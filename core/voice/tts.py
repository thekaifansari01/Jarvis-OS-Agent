import os
import re
import time
import asyncio
import threading
import logging
import queue
import requests
from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

load_dotenv()

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    pygame.mixer.init(frequency=24000, buffer=2048)
except Exception as e:
    logging.critical(f"CRITICAL: Failed to initialize Pygame Mixer: {e}")

TTS_API_KEY = os.getenv("TTS_API_KEY")
TTS_MODEL = os.getenv("TTS_MODEL")
TTS_VOICE = os.getenv("TTS_VOICE")
TTS_ENDPOINT = os.getenv("TTS_ENDPOINT")

from core.brain.config import EDGE_TTS_VOICE
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logging.warning("WARNING: edge-tts module not found. Fallback will not work. Install via 'pip install edge-tts'.")

_stop_playback = False
is_speaking = False
_tts_limit_reached = False
_audio_queue = queue.Queue()
_start_time = 0

def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""
    try:
        text = re.sub(r'http[s]?://\S+', 'this link', text)
        text = re.sub(r'```.*?```', 'this code', text, flags=re.DOTALL)
        clean = re.sub(r'[\*\_\#\`\-\>\~]', '', text)
        return re.sub(r'\s+', ' ', clean).strip()
    except Exception as e:
        logging.error(f"Error during text cleaning: {e}")
        return text.strip()

def smart_split_into_sentences(text: str) -> list:
    try:
        regex_pattern = r'(?<!\bMr)(?<!\bDr)(?<!\bMs)(?<!\bMrs)(?<!\bProf)\s*[.!?\n]\s+'
        sentences = re.split(regex_pattern, text)
        final_chunks = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(s) > 180:
                sub_chunks = [sc.strip() for sc in s.split(',') if sc.strip()]
                for sub in sub_chunks:
                    if len(sub) > 180:
                        final_chunks.extend([sub[i:i+180] for i in range(0, len(sub), 180)])
                    else:
                        final_chunks.append(sub)
            else:
                final_chunks.append(s)
        return final_chunks
    except Exception as e:
        logging.error(f"Error splitting sentences: {e}")
        return [text[:180]]

def stop_speaking():
    global _stop_playback, is_speaking, _audio_queue
    _stop_playback = True
    is_speaking = False
    try:
        pygame.mixer.stop()
    except Exception as exc:
        logging.debug("Unable to stop the pygame mixer: %s", exc, exc_info=True)

    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
            _audio_queue.task_done()
        except queue.Empty:
            break

async def _fetch_edge_tts_fallback(sentence: str) -> bytes:
    try:
        clean_sentence = re.sub(r'\[.*?\]', '', sentence).strip()
        if not clean_sentence:
            return b""

        communicate = edge_tts.Communicate(clean_sentence, EDGE_TTS_VOICE, rate='+30%', pitch='+5Hz')
        audio_bytes = bytearray()

        async for chunk in communicate.stream():
            if _stop_playback:
                break
            if chunk["type"] == "audio":
                audio_bytes.extend(chunk["data"])

        return bytes(audio_bytes)
    except Exception as e:
        logging.error(f"Edge TTS fallback generation failed: {e}")
        return b""

def _producer_thread(sentences: list):
    global _stop_playback, _audio_queue, _tts_limit_reached

    headers = {
        "Authorization": f"Bearer {TTS_API_KEY}",
        "Content-Type": "application/json"
    }

    for sentence in sentences:
        if _stop_playback:
            break

        audio_data = None

        if TTS_API_KEY and not _tts_limit_reached:
            data = {
                "model": TTS_MODEL,
                "input": sentence,
                "voice": TTS_VOICE,
                "response_format": "wav",
            }
            try:
                response = requests.post(TTS_ENDPOINT, json=data, headers=headers, timeout=7)
                if response.status_code == 200:
                    audio_data = response.content
                else:
                    if response.status_code == 429 or "limit" in response.text.lower() or "quota" in response.text.lower():
                        _tts_limit_reached = True
                    logging.error(f"TTS API Error ({response.status_code}): {response.text}. Switching to Fallback.")
            except Exception as e:
                logging.error(f"TTS API fetch connection failed: {e}. Switching to Fallback.")

        if not audio_data and EDGE_TTS_AVAILABLE:
            try:
                audio_data = asyncio.run(_fetch_edge_tts_fallback(sentence))
            except Exception as e:
                logging.error(f"Async execution for Edge-TTS failed: {e}")

        if audio_data and not _stop_playback:
            _audio_queue.put(audio_data)

    try:
        _audio_queue.put(None, timeout=2)
    except queue.Full:
        pass

def _consumer_thread():
    global _stop_playback, _audio_queue, _start_time
    first_chunk = True

    SPEED_MULTIPLIER = 1.25

    while not _stop_playback:
        try:
            chunk = _audio_queue.get(timeout=5.0)
        except queue.Empty:
            break

        if chunk is None:
            _audio_queue.task_done()
            break

        if not chunk or len(chunk) < 100:
            _audio_queue.task_done()
            continue

        chunk_array = bytearray(chunk)
        try:
            if chunk_array[0:4] == b'RIFF' and chunk_array[8:12] == b'WAVE':
                offset = 12
                while offset < len(chunk_array) - 8:
                    chunk_id = chunk_array[offset:offset+4]
                    chunk_size = int.from_bytes(chunk_array[offset+4:offset+8], 'little')

                    if chunk_id == b'fmt ':
                        sr_idx = offset + 8 + 4
                        old_sr = int.from_bytes(chunk_array[sr_idx:sr_idx+4], 'little')

                        new_sr = int(old_sr * SPEED_MULTIPLIER)
                        if new_sr > 48000:
                            new_sr = 48000

                        chunk_array[sr_idx:sr_idx+4] = new_sr.to_bytes(4, 'little')

                        br_idx = offset + 8 + 8
                        old_br = int.from_bytes(chunk_array[br_idx:br_idx+4], 'little')
                        new_br = int(old_br * (new_sr / max(1, old_sr)))
                        chunk_array[br_idx:br_idx+4] = new_br.to_bytes(4, 'little')
                        break

                    offset += 8 + chunk_size
        except Exception as e:
            pass

        try:
            audio_file = BytesIO(chunk_array)
            sound = pygame.mixer.Sound(audio_file)
        except Exception as primary_e:
            try:
                sound = pygame.mixer.Sound(BytesIO(chunk))
            except Exception as fallback_e:
                logging.error(f"Pygame fatal playback error: {fallback_e}")
                _audio_queue.task_done()
                continue

        if first_chunk:
            print(f"⚡ Asli Reaction Time (Text se Aawaz tak): {time.time() - _start_time:.2f} seconds!")
            first_chunk = False

        sound.play()

        while pygame.mixer.get_busy():
            if _stop_playback:
                pygame.mixer.stop()
                break
            pygame.time.Clock().tick(40)

        _audio_queue.task_done()

def speak(text: str):
    global _stop_playback, is_speaking, _audio_queue, _start_time

    if not text:
        return

    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return

    if is_speaking:
        stop_speaking()
        time.sleep(0.05)

    _stop_playback = False
    is_speaking = True
    _start_time = time.time()

    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
        except queue.Empty:
            break

    sentences = smart_split_into_sentences(cleaned)
    if not sentences:
        is_speaking = False
        return

    prod_thread = threading.Thread(target=_producer_thread, args=(sentences,), daemon=True)
    prod_thread.start()

    _consumer_thread()

    is_speaking = False

def cleanup_temp():
    stop_speaking()

if __name__ == "__main__":
    print("System Online. Testing Unified Audio Engine...")

    speak("[cheerful] Hello boss! System is live. Testing the primary TTS pipeline.")

    print("\n--- Testing continuous multi-sentence streaming ---")
    speak("[excited] This engine is awesome! [serious] It handles network drops like a champ. [friendly] No more ffplay dependencies!")

    print("Action Complete!")