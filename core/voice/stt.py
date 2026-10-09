import os
import sys
import time
import shutil
import zipfile
import threading
import queue
import urllib.request
import pyaudio
import json
import webrtcvad
from vosk import Model as VoskModel, KaldiRecognizer, SetLogLevel
from dotenv import load_dotenv

from core.logger.logger import logger
from core.voice.stt_status import update_stt_status
from core.voice import interrupt
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

load_dotenv()
SetLogLevel(-1)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

if not DEEPGRAM_API_KEY:
    logger.error("DEEPGRAM_API_KEY missing in .env file!")
else:
    logger.info("Deepgram API Key found.")

deepgram = DeepgramClient(DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY else None
update_stt_status("idle", "")

VOSK_MODEL_NAME = "vosk-model-small-en-in-0.4"
VOSK_MODEL_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL_NAME}.zip"
VOSK_MODEL_PATH = "Data/model/vosk-model-small"
VOSK_DOWNLOAD_DIR = "Data/model/_download"


def download_vosk_model():
    os.makedirs(VOSK_DOWNLOAD_DIR, exist_ok=True)
    zip_path = os.path.join(VOSK_DOWNLOAD_DIR, f"{VOSK_MODEL_NAME}.zip")

    logger.info(f"Downloading Vosk model from {VOSK_MODEL_URL} ...")

    last_percent = [-1]

    def _reporthook(block_num, block_size, total_size):
        if total_size > 0:
            downloaded = block_num * block_size
            percent = min(100, downloaded * 100 // total_size)
            if percent != last_percent[0]:
                last_percent[0] = percent
                bar_length = 30
                filled = int(bar_length * percent // 100)
                bar = "█" * filled + "░" * (bar_length - filled)
                sys.stdout.write(f"\r  Vosk model download: [{bar}] {percent}%")
                sys.stdout.flush()

    try:
        urllib.request.urlretrieve(VOSK_MODEL_URL, zip_path, reporthook=_reporthook)
        sys.stdout.write("\n")
        sys.stdout.flush()
        logger.info("Vosk model download complete. Extracting...")

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(VOSK_DOWNLOAD_DIR)

        extracted_path = os.path.join(VOSK_DOWNLOAD_DIR, VOSK_MODEL_NAME)

        if not os.path.exists(extracted_path):
            for item in os.listdir(VOSK_DOWNLOAD_DIR):
                full = os.path.join(VOSK_DOWNLOAD_DIR, item)
                if os.path.isdir(full) and item.startswith("vosk-model"):
                    extracted_path = full
                    break

        if not os.path.exists(extracted_path):
            raise RuntimeError("Extracted Vosk model folder not found.")

        if os.path.exists(VOSK_MODEL_PATH):
            shutil.rmtree(VOSK_MODEL_PATH)

        os.makedirs(os.path.dirname(VOSK_MODEL_PATH), exist_ok=True)
        shutil.move(extracted_path, VOSK_MODEL_PATH)
        logger.info(f"Vosk model ready at: {VOSK_MODEL_PATH}")

    except Exception as e:
        sys.stdout.write("\n")
        sys.stdout.flush()
        logger.error(f"Failed to download Vosk model: {e}", exc_info=True)
        raise
    finally:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass
        if os.path.exists(VOSK_DOWNLOAD_DIR):
            try:
                shutil.rmtree(VOSK_DOWNLOAD_DIR)
            except Exception:
                pass


class UnifiedVoiceAssistant:
    def __init__(self):
        self.mic_available = False
        self.running = True
        self.command_queue = queue.Queue()
        self.vosk_recognizer = None
        self.audio = None
        self.stream = None
        self.dg_connection = None
        self.is_awake = False
        self.connection_established = False
        self.RATE = 16000
        self.CHUNK = 480

        try:
            self.vad = webrtcvad.Vad(2)
            self.MAX_SILENCE_TIMEOUT = 1.0
            self.MAX_WAIT_TIMEOUT = 4.0

            self.WAKE_WORDS = ["jarvis", "hey jarvis"]
            self.DECOY_WORDS = [
                "hello", "computer", "hi", "okay", "yes", "no", "stop",
                "test", "mike", "testing", "one",
                "two", "three", "alpha", "beta", "noise", "background", "something"
            ]

            model_path = VOSK_MODEL_PATH
            if not os.path.exists(model_path):
                logger.warning(f"Vosk model not found at '{model_path}'. Auto-downloading...")
                download_vosk_model()

            self.vosk_model = VoskModel(model_path)

            grammar = json.dumps(self.WAKE_WORDS + self.DECOY_WORDS + ["[unk]"])
            self.vosk_recognizer = KaldiRecognizer(self.vosk_model, self.RATE, grammar)

            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )

            self.current_transcript = ""
            self.live_text = ""
            self.command_done = threading.Event()
            self.last_speech_time = 0
            self.wake_time = 0
            self.has_spoken = False

            self.mic_available = True
            logger.info("Microphone initialized successfully. Voice input ENABLED.")

        except Exception as e:
            self.mic_available = False
            logger.warning(f"Microphone not available — voice input DISABLED. Reason: {e}")

    def start(self):
        if not self.mic_available:
            logger.warning("🎤 Mic not available. Skipping audio loop start.")
            return
        logger.info("🎧 Wake word listener thread starting...")
        self.listen_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.listen_thread.start()
        logger.info("✅ Wake word listener active. Listening for 'Jarvis' / 'Hey Jarvis'...")

    def play_wake_sound(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception as e:
            logger.error(f"Wake sound error: {e}")

    def _flush_audio_buffer(self):
        if not self.stream:
            return
        try:
            available = self.stream.get_read_available()
            if available > 0:
                self.stream.read(available, exception_on_overflow=False)
        except Exception as e:
            logger.error(f"Buffer flush error: {e}")

    def _setup_deepgram(self):
        self.current_transcript = ""
        self.live_text = ""
        self.command_done.clear()
        assistant = self

        try:
            self.dg_connection = deepgram.listen.websocket.v("1")

            def on_message(dg_self, result, **kwargs):
                sentence = result.channel.alternatives[0].transcript
                if sentence:
                    if result.is_final:
                        assistant.current_transcript += " " + sentence
                        assistant.live_text = assistant.current_transcript.strip()
                    else:
                        assistant.live_text = (assistant.current_transcript + " " + sentence).strip()
                    update_stt_status("listening", assistant.live_text)

                if getattr(result, 'speech_final', False) and assistant.live_text.strip():
                    assistant.command_done.set()

            def on_utterance_end(dg_self, utterance_end, **kwargs):
                if assistant.live_text.strip():
                    assistant.command_done.set()

            def on_error(dg_self, error, **kwargs):
                logger.error(f"Deepgram Error: {error}")
                assistant.command_done.set()

            self.dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
            self.dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
            self.dg_connection.on(LiveTranscriptionEvents.Error, on_error)

            options = LiveOptions(
                model="nova-2",
                language="hi",
                keywords=["Jarvis:4", "Mindly:3", "Llama:2", "Gemini:2", "Kaif:3", "Youtube", "Google", "ansari"],
                smart_format=True,
                interim_results=True,
                vad_events=True,
                endpointing=800,
                utterance_end_ms="1000",
                encoding="linear16",
                channels=1,
                sample_rate=self.RATE,
            )

            if not self.dg_connection.start(options):
                logger.error("❌ Failed to start Deepgram websocket connection.")
                return False

            logger.info("🔗 Deepgram websocket connected successfully.")
            return True

        except Exception as e:
            logger.error(f"❌ Deepgram setup exception: {e}", exc_info=True)
            return False

    def _check_wake_word(self, text):
        clean_text = text.lower().strip()
        if not clean_text:
            return False
        for wake in self.WAKE_WORDS:
            if wake in clean_text:
                return True
        return False

    def _audio_loop(self):
        if not self.mic_available:
            return

        while self.running:
            try:
                pcm_data = self.stream.read(self.CHUNK, exception_on_overflow=False)

                if not self.is_awake:
                    is_speech = self.vad.is_speech(pcm_data, self.RATE)
                    triggered = False

                    if is_speech:
                        if self.vosk_recognizer.AcceptWaveform(pcm_data):
                            res = json.loads(self.vosk_recognizer.Result())
                            text = res.get("text", "")
                        else:
                            res = json.loads(self.vosk_recognizer.PartialResult())
                            text = res.get("partial", "")

                        if self._check_wake_word(text):
                            triggered = True

                    if triggered:
                        logger.info(f"🎯 Wake word detected | matched_text='{text}'")

                        try:
                            from core.voice import tts
                            tts.stop_speaking()
                        except Exception:
                            pass

                        interrupt.set_interrupt()
                        self._flush_audio_buffer()
                        self.vosk_recognizer.Reset()
                        self.play_wake_sound()
                        update_stt_status("connecting", "Listening...")

                        if not self.connection_established or self.dg_connection is None:
                            logger.info("🔌 Establishing Deepgram connection...")
                            if self._setup_deepgram():
                                self.connection_established = True
                                logger.info("✅ Deepgram connection established.")
                            else:
                                logger.warning("⚠️ Deepgram connection failed. Returning to wake word mode.")
                                self.connection_established = False
                                self.vosk_recognizer.Reset()
                                continue

                        self.wake_time = time.time()
                        self.last_speech_time = time.time()
                        self.has_spoken = False
                        self.is_awake = True
                        logger.info("👂 User command listening STARTED (max wait 4.0s, silence timeout 1.0s).")
                        update_stt_status("listening", "Listening...")

                else:
                    is_speech = self.vad.is_speech(pcm_data, self.RATE)
                    current_time = time.time()

                    if is_speech:
                        self.last_speech_time = current_time
                        self.has_spoken = True

                    if not self.has_spoken and (current_time - self.wake_time > self.MAX_WAIT_TIMEOUT):
                        logger.info("⏱️ No speech detected within 4.0s after wake word. Ending command capture.")
                        self.command_done.set()

                    elif self.has_spoken and (current_time - self.last_speech_time > self.MAX_SILENCE_TIMEOUT):
                        logger.info("⏱️ Silence timeout (1.0s) reached after speech. Finalizing command.")
                        self.command_done.set()

                    if self.dg_connection:
                        try:
                            self.dg_connection.send(pcm_data)
                        except Exception as e:
                            logger.error(f"❌ Lost Deepgram connection while sending audio: {e}")
                            self._force_sleep_reset()
                            continue

                    if self.command_done.is_set():
                        self.process_final_command()

            except Exception as e:
                logger.error(f"Audio loop error: {e}")
                time.sleep(0.01)

    def _force_sleep_reset(self):
        logger.warning("🔄 Force sleep reset triggered. Returning to wake word mode.")
        self.dg_connection = None
        self.connection_established = False
        self.is_awake = False
        self._flush_audio_buffer()
        if self.vosk_recognizer:
            self.vosk_recognizer.Reset()
        update_stt_status("idle", "")
        logger.info("💤 Back to idle. Listening for wake word...")

    def process_final_command(self):
        full_command = self.live_text.lower().strip()
        ignore_words = ["", "okay", "okay.", "jarvis", "jarvis.", "thanks", "thank you",
                        "hmm", "haan", "ah", "uh", "theek hai", "hello", "ha"]

        logger.info("🛑 User command listening STOPPED. Processing transcript...")
        logger.info(f"📝 Raw transcript received: '{full_command}'")

        self.is_awake = False

        try:
            if self.dg_connection:
                self.dg_connection.finish()
        except Exception as e:
            logger.error(f"❌ Error finishing Deepgram connection: {e}")
        finally:
            self.dg_connection = None
            self.connection_established = False

        self._flush_audio_buffer()
        if self.vosk_recognizer:
            self.vosk_recognizer.Reset()
        interrupt.clear_interrupt()

        if full_command and full_command not in ignore_words and len(full_command) > 3:
            logger.info(f"✅ Valid command accepted -> '{full_command}'")
            update_stt_status("understanding", full_command)
            self.command_queue.put(full_command)
        else:
            logger.info(f"🚫 Command rejected (empty/ignore-list/too short) -> returning to wake mode.")
            update_stt_status("idle", "")
            self.command_queue.put("")

        logger.info("💤 Idle. Waiting for next wake word 'Jarvis'...")
        time.sleep(0.2)

    def get_command(self, is_retry=False):
        command = None
        while self.running:
            try:
                command = self.command_queue.get(timeout=0.5)
                break
            except queue.Empty:
                continue

        if not self.running or command is None:
            return ""

        if command:
            logger.info(f"📤 Command delivered to processor: '{command}'")

        return command

    def stop(self):
        logger.info("🛑 Stopping voice engine...")
        self.running = False
        try:
            if self.dg_connection:
                self.dg_connection.finish()
        except Exception:
            pass
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
        except Exception:
            pass
        try:
            if self.audio:
                self.audio.terminate()
        except Exception:
            pass
        logger.info("✅ Voice engine stopped.")


try:
    engine = UnifiedVoiceAssistant()
except Exception as e:
    logger.critical(f"Failed to initialize voice engine: {e}. Falling back to dummy engine.")

    class _DummyEngine:
        mic_available = False

        def __init__(self):
            self.mic_available = False
            self.running = False

        def start(self):
            pass

        def stop(self):
            pass

        def get_command(self, is_retry=False):
            return ""

    engine = _DummyEngine()


def start_background_wake_word_listener():
    engine.start()


def listen():
    if not getattr(engine, 'mic_available', False):
        return ""
    return engine.get_command()


if __name__ == "__main__":
    try:
        start_background_wake_word_listener()
        logger.info("Voice module ready")
        while True:
            command = listen()
            if command:
                pass
    except KeyboardInterrupt:
        engine.stop()
    except Exception as e:
        logger.error(f"Main loop fatal error: {e}", exc_info=True)
        engine.stop()