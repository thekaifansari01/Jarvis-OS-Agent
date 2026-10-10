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
    logger.info("🔊 Pygame Mixer initialized successfully. Audio output ENABLED.")
except Exception as e:
    logger.critical(f"❌ Failed to initialize Pygame Mixer: {e}")
    logger.warning("🔇 Audio output device not available — TTS will run in text-only mode.")

TTS_API_KEY = os.getenv("TTS_API_KEY")
TTS_ENDPOINT = os.getenv("TTS_ENDPOINT")

from core.brain.config import EDGE_TTS_VOICE
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
    logger.info("✅ edge-tts module loaded. Fallback TTS available.")
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("⚠️ edge-tts module not found. Fallback TTS DISABLED.")

_stop_playback = False
is_speaking = False
_tts_limit_reached = False
_audio_queue = queue.Queue()
_start_time = 0


def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""
    try:
        original_len = len(text)
        text = re.sub(r'http[s]?://\S+', 'this link', text)
        text = re.sub(r'```.*?```', 'this code', text, flags=re.DOTALL)
        clean = re.sub(r'[\*\_\#\`\-\>\~]', '', text)
        result = re.sub(r'\s+', ' ', clean).strip()
        logger.debug(f"🧹 Text cleaned | original={original_len} chars | cleaned={len(result)} chars")
        return result
    except Exception as e:
        logger.error(f"❌ Error during text cleaning: {e}")
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
        logger.debug(f"✂️ Sentence split complete | chunks={len(final_chunks)}")
        return final_chunks
    except Exception as e:
        logger.error(f"❌ Error splitting sentences: {e}")
        return [text[:180]]


def stop_speaking():
    global _stop_playback, is_speaking, _audio_queue
    logger.info("🛑 TTS stop_speaking() invoked. Interrupting current playback...")
    _stop_playback = True
    is_speaking = False

    if not _audio_output_available:
        logger.debug("Audio output not available, skipping mixer stop.")
        return

    try:
        pygame.mixer.stop()
    except Exception as exc:
        logger.debug(f"Unable to stop the pygame mixer: {exc}")

    cleared = 0
    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
            _audio_queue.task_done()
            cleared += 1
        except queue.Empty:
            break

    if cleared > 0:
        logger.info(f"🗑️ Audio queue cleared | discarded_chunks={cleared}")


async def _fetch_edge_tts_fallback(sentence: str) -> bytes:
    try:
        clean_sentence = re.sub(r'\[.*?\]', '', sentence).strip()
        if not clean_sentence:
            return b""

        logger.info(f"🌐 Edge-TTS fallback generating audio | text='{clean_sentence[:50]}...'")
        communicate = edge_tts.Communicate(clean_sentence, EDGE_TTS_VOICE, rate='+5%', pitch='-6Hz')
        audio_bytes = bytearray()

        async for chunk in communicate.stream():
            if _stop_playback:
                logger.debug("Edge-TTS stream interrupted by stop_playback flag.")
                break
            if chunk["type"] == "audio":
                audio_bytes.extend(chunk["data"])

        logger.info(f"✅ Edge-TTS audio ready | bytes={len(audio_bytes)}")
        return bytes(audio_bytes)
    except Exception as e:
        logger.error(f"❌ Edge TTS fallback generation failed: {e}")
        return b""


def _producer_thread(sentences: list):
    global _stop_playback, _audio_queue, _tts_limit_reached

    logger.info(f"🎬 Producer thread started | total_sentences={len(sentences)}")

    headers = {
        "api-subscription-key": TTS_API_KEY,
        "Content-Type": "application/json"
    }

    sarvam_count = 0
    edge_count = 0
    failed_count = 0

    for idx, sentence in enumerate(sentences, 1):
        if _stop_playback:
            logger.info(f"⏹️ Producer thread stopping early at sentence {idx}/{len(sentences)}")
            break

        audio_data = None

        if TTS_API_KEY and not _tts_limit_reached:
            data = {
                "inputs": [sentence],
                "target_language_code": "hi-IN",
                "speaker": "aditya_hi_conversational",
                "model": "bulbul:v4-flash",
                "pace": 1,
                "speech_sample_rate": 24000
            }
            try:
                logger.debug(f"📡 Sarvam TTS request | sentence {idx}/{len(sentences)}")
                response = requests.post(TTS_ENDPOINT, json=data, headers=headers, timeout=10)
                if response.status_code == 200:
                    response_json = response.json()
                    if "audios" in response_json and len(response_json["audios"]) > 0:
                        audio_data = base64.b64decode(response_json["audios"][0])
                        sarvam_count += 1
                        logger.debug(f"✅ Sarvam TTS success | sentence {idx} | bytes={len(audio_data)}")
                else:
                    if response.status_code == 429 or "limit" in response.text.lower() or "quota" in response.text.lower():
                        _tts_limit_reached = True
                        logger.warning(f"⚠️ Sarvam TTS quota/limit reached (status={response.status_code}). Switching to Edge-TTS fallback.")
                    logger.error(f"❌ TTS API Error ({response.status_code}): {response.text[:200]}")
            except Exception as e:
                logger.error(f"❌ TTS API fetch connection failed: {e}")

        if not audio_data and EDGE_TTS_AVAILABLE:
            try:
                audio_data = asyncio.run(_fetch_edge_tts_fallback(sentence))
                if audio_data:
                    edge_count += 1
            except Exception as e:
                logger.error(f"❌ Async execution for Edge-TTS failed: {e}")

        if audio_data and not _stop_playback:
            _audio_queue.put(audio_data)
            logger.debug(f"📥 Audio chunk queued | sentence {idx}/{len(sentences)} | queue_size={_audio_queue.qsize()}")
        elif not audio_data:
            failed_count += 1
            logger.warning(f"⚠️ No audio generated for sentence {idx}/{len(sentences)}")

    try:
        _audio_queue.put(None, timeout=2)
        logger.info(f"🏁 Producer thread finished | sarvam={sarvam_count} | edge={edge_count} | failed={failed_count}")
    except queue.Full:
        logger.warning("⚠️ Failed to put sentinel in audio queue — queue full.")


def _consumer_thread():
    global _stop_playback, _audio_queue, _start_time
    first_chunk = True
    chunks_played = 0

    SPEED_MULTIPLIER = 1.0

    while not _stop_playback:
        try:
            chunk = _audio_queue.get(timeout=5.0)
        except queue.Empty:
            logger.info("⏱️ Audio queue empty timeout (5s). Consumer thread exiting.")
            break

        if chunk is None:
            _audio_queue.task_done()
            logger.info(f"🏁 Consumer thread received sentinel. Total chunks played={chunks_played}")
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
            logger.debug(f"WAV header patch skipped: {e}")

        try:
            audio_file = BytesIO(chunk_array)
            sound = pygame.mixer.Sound(audio_file)
        except Exception as patch_err:
            logger.debug(f"Pygame playback with patched array failed ({patch_err}), retrying with original chunk.")
            try:
                sound = pygame.mixer.Sound(BytesIO(chunk))
            except Exception as fallback_e:
                logger.error(f"❌ Pygame fatal playback error: {fallback_e}")
                _audio_queue.task_done()
                continue

        if first_chunk:
            reaction_time = time.time() - _start_time
            logger.info(f"⚡ First audio playback starting | reaction_time={reaction_time:.2f}s")
            print(f"⚡ Asli Reaction Time (Text se Aawaz tak): {reaction_time:.2f} seconds!")
            first_chunk = False

        sound.play()
        chunks_played += 1
        logger.debug(f"🔊 Playing chunk #{chunks_played} | size={len(chunk)} bytes")

        while pygame.mixer.get_busy():
            if _stop_playback:
                logger.info(f"⏹️ Playback interrupted mid-chunk #{chunks_played}")
                pygame.mixer.stop()
                break
            pygame.time.Clock().tick(40)

        _audio_queue.task_done()


def speak(text: str):
    global _stop_playback, is_speaking, _audio_queue, _start_time

    if not text:
        logger.debug("speak() called with empty text — ignoring.")
        return

    if not _audio_output_available:
        cleaned = clean_text_for_speech(text)
        if cleaned:
            logger.info(f"🔇 Text-only mode output | chars={len(cleaned)}")
            print(f"🤖 JARVIS (text-only): {cleaned}")
        return

    cleaned = clean_text_for_speech(text)
    if not cleaned:
        logger.debug("Cleaned text is empty — nothing to speak.")
        return

    if is_speaking:
        logger.info("⚠️ TTS already speaking. Interrupting current playback for new speech.")
        stop_speaking()
        time.sleep(0.05)

    _stop_playback = False
    is_speaking = True
    _start_time = time.time()

    logger.info(f"🎙️ TTS speak() started | text_length={len(cleaned)} chars")

    cleared = 0
    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
            cleared += 1
        except queue.Empty:
            break
    if cleared > 0:
        logger.debug(f"🗑️ Pre-speak queue cleared | discarded={cleared}")

    sentences = smart_split_into_sentences(cleaned)
    if not sentences:
        is_speaking = False
        logger.warning("⚠️ No sentences generated after split — aborting speak().")
        return

    logger.info(f"📝 Speech prepared | sentences={len(sentences)}")

    prod_thread = threading.Thread(target=_producer_thread, args=(sentences,), daemon=True)
    prod_thread.start()

    _consumer_thread()

    is_speaking = False
    logger.info("✅ TTS speak() completed.")


def cleanup_temp():
    logger.info("🧹 TTS cleanup_temp() invoked.")
    stop_speaking()


if __name__ == "__main__":
    print("System Online. Testing Unified Audio Engine...")
    speak("Namaste boss! System is live. Testing the primary TTS pipeline.")
    print("\n--- Testing continuous multi-sentence streaming ---")
    speak("This engine is awesome! It handles network drops like a champ. No more dependencies!")
    print("Action Complete!")