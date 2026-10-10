import os
import re
import time
import asyncio
import threading
import queue
import requests
import base64
from io import BytesIO
from dotenv import load_dotenv

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

load_dotenv()

from core.logger.logger import logger

_audio_output_available = False
try:
    pygame.mixer.init(frequency=24000, buffer=2048)
    _audio_output_available = True
    logger.info("Audio output enabled")
except Exception as e:
    logger.error(f"Audio init failed: {e}. Running in text-only mode.")

TTS_API_KEY = os.getenv("TTS_API_KEY")
TTS_ENDPOINT = os.getenv("TTS_ENDPOINT")

from core.brain.config import EDGE_TTS_VOICE

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
    logger.info("Edge-TTS fallback ready")
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("Edge-TTS not available")

_stop_playback = False
is_speaking = False
_tts_limit_reached = False
_audio_queue = queue.Queue()
_start_time = 0

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U0001F700-\U0001F77F"
    "\U00002B00-\U00002BFF"
    "\U0001F000-\U0001F02F"
    "]+",
    flags=re.UNICODE
)


def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""
    try:
        text = re.sub(r'```.*?```', ' code ', text, flags=re.DOTALL)
        text = re.sub(r'`([^`]*)`', r'\1', text)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
        text = re.sub(r'http[s]?://\S+', ' link ', text)
        text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[\*\-\+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'(\*\*|\*|__|_|~~)', '', text)
        text = re.sub(r'\|', ' ', text)
        text = EMOJI_PATTERN.sub(' ', text)
        text = re.sub(r'[\u200B-\u200F\u202A-\u202E\uFEFF]', '', text)
        text = re.sub(r'[/\\@^~<>]', ' ', text)
        text = re.sub(r'\.{3,}', '.', text)
        text = re.sub(r'[!?]{2,}', lambda m: m.group()[0], text)
        text = re.sub(r'[,;:]{2,}', ',', text)
        text = re.sub(r'\(\s*\)', '', text)
        text = re.sub(r'\[\s*\]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    except Exception as e:
        logger.error(f"Text cleaning error: {e}")
        return text.strip()


def smart_split_into_sentences(text: str) -> list:
    try:
        pattern = r'(?<!\bMr)(?<!\bDr)(?<!\bMs)(?<!\bMrs)(?<!\bProf)(?<!\be\.g)(?<!\bi\.e)(?<!\betc)(?<!\bvs)\s*[.!?\n]\s+'
        sentences = re.split(pattern, text)
        final_chunks = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(s) > 180:
                for sub in [sc.strip() for sc in s.split(',') if sc.strip()]:
                    if len(sub) > 180:
                        final_chunks.extend([sub[i:i+180] for i in range(0, len(sub), 180)])
                    else:
                        final_chunks.append(sub)
            else:
                final_chunks.append(s)
        return final_chunks
    except Exception as e:
        logger.error(f"Sentence split error: {e}")
        return [text[:180]]


def stop_speaking():
    global _stop_playback, is_speaking, _audio_queue
    logger.debug("Stopping TTS playback")
    _stop_playback = True
    is_speaking = False

    if _audio_output_available:
        try:
            pygame.mixer.stop()
        except Exception:
            pass

    cleared = 0
    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
            _audio_queue.task_done()
            cleared += 1
        except queue.Empty:
            break

    if cleared:
        logger.debug(f"Cleared {cleared} queued audio chunks")


async def _fetch_edge_tts_fallback(sentence: str) -> bytes:
    try:
        clean_sentence = re.sub(r'\[.*?\]', '', sentence).strip()
        if not clean_sentence:
            return b""

        communicate = edge_tts.Communicate(
            clean_sentence, EDGE_TTS_VOICE, rate='+18%', pitch='-4Hz'
        )
        audio_bytes = bytearray()
        async for chunk in communicate.stream():
            if _stop_playback:
                break
            if chunk["type"] == "audio":
                audio_bytes.extend(chunk["data"])
        return bytes(audio_bytes)
    except Exception as e:
        logger.error(f"Edge-TTS failed: {e}")
        return b""


def _producer_thread(sentences: list):
    global _stop_playback, _audio_queue, _tts_limit_reached

    headers = {
        "api-subscription-key": TTS_API_KEY,
        "Content-Type": "application/json"
    }

    sarvam_count = 0
    edge_count = 0
    failed_count = 0

    for idx, sentence in enumerate(sentences, 1):
        if _stop_playback:
            break

        audio_data = None

        if TTS_API_KEY and not _tts_limit_reached:
            payload = {
                "inputs": [sentence],
                "target_language_code": "hi-IN",
                "speaker": "aditya_hi_conversational",
                "model": "bulbul:v4-flash",
                "pace": 1.25,
                "speech_sample_rate": 24000
            }

            for attempt in range(2):
                try:
                    response = requests.post(
                        TTS_ENDPOINT, json=payload, headers=headers, timeout=10
                    )
                    if response.status_code == 200:
                        body = response.json()
                        if body.get("audios"):
                            audio_data = base64.b64decode(body["audios"][0])
                            sarvam_count += 1
                        break
                    if (response.status_code == 429
                            or "limit" in response.text.lower()
                            or "quota" in response.text.lower()):
                        _tts_limit_reached = True
                        logger.warning("Sarvam quota reached, using Edge-TTS")
                        break
                    logger.error(f"Sarvam TTS error {response.status_code}")
                    break
                except Exception as e:
                    if attempt == 0:
                        continue
                    logger.error(f"Sarvam TTS request failed: {e}")

        if not audio_data and EDGE_TTS_AVAILABLE and not _stop_playback:
            try:
                audio_data = asyncio.run(_fetch_edge_tts_fallback(sentence))
                if audio_data:
                    edge_count += 1
            except Exception as e:
                logger.error(f"Edge-TTS execution failed: {e}")

        if audio_data and not _stop_playback:
            _audio_queue.put(audio_data)
        elif not audio_data:
            failed_count += 1

    try:
        _audio_queue.put(None, timeout=5)
    except queue.Full:
        logger.warning("Audio queue full, sentinel not queued")

    logger.info(
        f"TTS producer done | sarvam={sarvam_count} edge={edge_count} failed={failed_count}"
    )


def _consumer_thread():
    global _stop_playback, _audio_queue, _start_time
    first_chunk = True
    chunks_played = 0
    clock = pygame.time.Clock()

    while not _stop_playback:
        try:
            chunk = _audio_queue.get(timeout=30.0)
        except queue.Empty:
            logger.debug("Consumer timeout waiting for audio")
            break

        if chunk is None:
            _audio_queue.task_done()
            break

        if not chunk or len(chunk) < 100:
            _audio_queue.task_done()
            continue

        try:
            sound = pygame.mixer.Sound(BytesIO(chunk))
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
            _audio_queue.task_done()
            continue

        if first_chunk:
            reaction_time = time.time() - _start_time
            logger.info(f"First audio in {reaction_time:.2f}s")
            first_chunk = False

        sound.play()
        chunks_played += 1

        while pygame.mixer.get_busy():
            if _stop_playback:
                pygame.mixer.stop()
                break
            clock.tick(40)

        _audio_queue.task_done()


def speak(text: str):
    global _stop_playback, is_speaking, _audio_queue, _start_time, _tts_limit_reached

    if not text:
        return

    if not _audio_output_available:
        cleaned = clean_text_for_speech(text)
        if cleaned:
            logger.info(f"TTS text-only: {cleaned}")
        return

    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return

    if is_speaking:
        stop_speaking()
        time.sleep(0.05)

    _tts_limit_reached = False
    _stop_playback = False
    is_speaking = True
    _start_time = time.time()

    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
            _audio_queue.task_done()
        except queue.Empty:
            break

    sentences = smart_split_into_sentences(cleaned)
    if not sentences:
        is_speaking = False
        return

    logger.info(f"TTS speaking | sentences={len(sentences)} chars={len(cleaned)}")

    try:
        producer = threading.Thread(target=_producer_thread, args=(sentences,), daemon=True)
        producer.start()
        _consumer_thread()
    finally:
        is_speaking = False


def cleanup_temp():
    stop_speaking()
    if _audio_output_available:
        try:
            pygame.mixer.quit()
        except Exception:
            pass


if __name__ == "__main__":
    speak("Namaste boss! System live hai. TTS pipeline test ho raha hai.")
    speak("Yeh engine network drops ko handle karta hai. Sab smooth chal raha hai.")