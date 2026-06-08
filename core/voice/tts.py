import os
import re
import time
import asyncio
import threading
import subprocess
import logging
import queue
from pathlib import Path

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

from core.brain.config import EDGE_TTS_VOICE

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logging.critical("CRITICAL: edge-tts module not found. Please install via 'pip install edge-tts'.")

_stop_playback = False
is_speaking = False
_current_process = None
_audio_queue = queue.Queue()

def clean_text_for_speech(text: str) -> str:
    """
    Prepares text for TTS by removing markdown, URLs, and code blocks.
    This ensures the AI sounds natural and doesn't verbally spell out symbols.
    """
    if not text:
        return ""
    
    try:
        text = re.sub(r'\[[a-zA-Z]+\]', '', text).strip()
        
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', 'this link', text)
        
        text = re.sub(r'```.*?```', 'this code', text, flags=re.DOTALL)
        
        clean = re.sub(r'[\*\_\#\`\-\[\]\>\~]', '', text)
        
        return re.sub(r'\s+', ' ', clean).strip()
    except Exception as e:
        logging.error(f"Error during text cleaning: {e}")
        return text.strip()

def smart_split_into_sentences(text: str) -> list:
    """
    Breaks long paragraphs into smaller chunks using punctuation.
    Advanced: Ignores common abbreviations (Mr., Dr.) to prevent unnatural pauses.
    """
    try:
        regex_pattern = r'(?<!\bMr)(?<!\bDr)(?<!\bMs)(?<!\bMrs)(?<!\bProf)\s*[.!?\n]\s+'
        sentences = re.split(regex_pattern, text)
        
        final_chunks = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
                
            if len(s) > 150 and ',' in s:
                sub_chunks = [sc.strip() for sc in s.split(',') if sc.strip()]
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(s)
                
        return final_chunks
    except Exception as e:
        logging.error(f"Error splitting sentences: {e}")
        return [text]

def _get_ffplay_path() -> str:
    """
    Locates the ffplay executable dynamically. Essential for audio streaming.
    """
    possible_paths = [
        r"C:\ffmpeg\bin\ffplay.exe",
        r"C:\Program Files\ffmpeg\bin\ffplay.exe",
        "ffplay"
    ]
    for p in possible_paths:
        try:
            if Path(p).exists():
                return p
            if p == "ffplay" and subprocess.run(["where", "ffplay"], capture_output=True, check=False).returncode == 0:
                return p
        except Exception:
            continue
            
    return None

def stop_speaking():
    """
    Instantly halts all TTS operations. Clears queues and forcefully kills playback.
    """
    global _stop_playback, is_speaking, _current_process, _audio_queue
    _stop_playback = True
    is_speaking = False

    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
            _audio_queue.task_done()
        except queue.Empty:
            break

    if _current_process:
        try:
            _current_process.kill()
        except OSError as e:
            logging.error(f"OS Error while killing ffplay: {e}")
        except Exception as e:
            logging.error(f"Unexpected error killing ffplay: {e}")
        finally:
            _current_process = None

async def _fetch_audio_chunks(sentence: str):
    """
    Asynchronously streams audio bytes from Edge TTS API and puts them into the queue.
    """
    global _audio_queue, _stop_playback
    try:
        communicate = edge_tts.Communicate(sentence, EDGE_TTS_VOICE, rate='+30%', pitch='+5Hz')
        
        async for chunk in communicate.stream():
            if _stop_playback:
                break
            if chunk["type"] == "audio":
                _audio_queue.put(chunk["data"])
                
    except asyncio.TimeoutError:
        if not _stop_playback:
            logging.error("Edge TTS API timed out. Network issue?")
    except Exception as e:
        if not _stop_playback:
            logging.error(f"Edge TTS fetch error: {e}")

def _producer_thread(sentences: list):
    """
    Runs the asynchronous fetcher in a background thread for each sentence.
    """
    global _stop_playback, _audio_queue
    
    for sentence in sentences:
        if _stop_playback:
            break
        try:
            asyncio.run(_fetch_audio_chunks(sentence))
        except Exception as e:
            logging.error(f"Producer thread failed on sentence: {e}")
    
    try:
        _audio_queue.put(None, timeout=2)
    except queue.Full:
        logging.warning("Audio queue full, could not send poison pill.")

def _consumer_thread():
    """
    Continuously reads audio bytes from the queue and pipes them to ffplay.
    """
    global _current_process, _stop_playback, _audio_queue
    
    ffplay_path = _get_ffplay_path()
    if not ffplay_path:
        logging.error("ffplay not found. Audio playback aborted. Install FFmpeg.")
        return

    stealth_flag = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    
    try:
        _current_process = subprocess.Popen(
            [ffplay_path, "-autoexit", "-nodisp", "-hide_banner", "-loglevel", "error",
             "-probesize", "32", "-analyzeduration", "0", "-sync", "ext", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=stealth_flag
        )
        
        while not _stop_playback:
            try:
                chunk = _audio_queue.get(timeout=5.0)
            except queue.Empty:
                if not _stop_playback:
                    logging.warning("Consumer queue timed out waiting for audio.")
                break
            
            if chunk is None:
                _audio_queue.task_done()
                break
                
            try:
                _current_process.stdin.write(chunk)
                _current_process.stdin.flush()
                _audio_queue.task_done()
            except (BrokenPipeError, OSError) as e:
                if not _stop_playback:
                    logging.warning(f"Audio pipe broken (ffplay may have closed): {e}")
                break

    except FileNotFoundError:
        logging.error("ffplay executable not found at the specified path.")
    except Exception as e:
        if not _stop_playback:
            logging.error(f"Unexpected playback error in consumer: {e}")
            
    finally:
        if _current_process:
            if _current_process.stdin:
                try:
                    _current_process.stdin.close()
                except Exception:
                    pass
            try:
                _current_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _current_process.kill()
            except Exception:
                pass
            finally:
                _current_process = None

def speak(text: str):
    """
    Entry point for TTS. Cleans text, interrupts current speech, and starts the Producer/Consumer threads.
    """
    global _stop_playback, is_speaking, _audio_queue

    if not text or not EDGE_TTS_AVAILABLE:
        return

    cleaned_for_speech = clean_text_for_speech(text)
    if not cleaned_for_speech:
        return

    if is_speaking:
        stop_speaking()
        time.sleep(0.05)

    _stop_playback = False
    is_speaking = True

    while not _audio_queue.empty():
        try: 
            _audio_queue.get_nowait()
            _audio_queue.task_done()
        except queue.Empty: 
            break

    sentences = smart_split_into_sentences(cleaned_for_speech)
    if not sentences:
        is_speaking = False
        return

    prod_thread = threading.Thread(target=_producer_thread, args=(sentences,), daemon=True)
    prod_thread.start()

    _consumer_thread()

    is_speaking = False

def cleanup_temp():
    """Placeholder for any external resource cleanup if needed during shutdown."""
    pass