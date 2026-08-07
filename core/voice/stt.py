import os
import time
import threading
import queue
import winsound
import pyaudio
import json
from vosk import Model as VoskModel, KaldiRecognizer, SetLogLevel
from datetime import datetime
from dotenv import load_dotenv

from core.logger.logger import logger
from core.voice.stt_status import update_stt_status
from core.voice import interrupt
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

load_dotenv()

SetLogLevel(-1)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

if not DEEPGRAM_API_KEY:
    logger.error("DEEPGRAM_API_KEY missing in .env")

deepgram = DeepgramClient(DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY else None
update_stt_status("idle", "")

class UnifiedVoiceAssistant:
    def __init__(self):
        self.CHUNK = 2048
        self.RATE = 16000
        self.WAKE_WORDS = ["jarvis"]

        model_path = "Data/model/vosk-model-small"
        if not os.path.exists(model_path):
            logger.error(f"Vosk model folder not found at: {model_path}")
            raise FileNotFoundError(f"Vosk model not found at '{model_path}'.")
        
        logger.info("Loading Vosk wake word model...")
        try:
            self.vosk_model = VoskModel(model_path)
            grammar = json.dumps(self.WAKE_WORDS + ["[unk]"])
            self.vosk_recognizer = KaldiRecognizer(self.vosk_model, self.RATE, grammar)
            logger.info("Vosk model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Vosk model: {e}")
            raise

        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK
        )

        self.is_awake = False
        self.running = True
        self.command_queue = queue.Queue()

        self.dg_connection = None
        self.current_transcript = ""
        self.live_text = ""
        self.command_done = threading.Event()

    def start(self):
        logger.info("Wake Word Detection Activated -> Listening for 'Jarvis'...")
        self.listen_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.listen_thread.start()

    def play_wake_sound(self):
        try:
            winsound.Beep(2000, 150)
        except Exception:
            pass

    def _setup_deepgram(self):
        self.current_transcript = ""
        self.live_text = ""
        self.command_done.clear()
        assistant = self

        try:
            self.dg_connection = deepgram.listen.live.v("1")

            def on_message(dg_self, result, **kwargs):
                sentence = result.channel.alternatives[0].transcript
                if result.is_final:
                    if sentence:
                        assistant.current_transcript += " " + sentence
                    assistant.live_text = assistant.current_transcript.strip()
                    update_stt_status("listening", assistant.live_text)
                    if getattr(result, 'speech_final', False):
                        assistant.command_done.set()
                else:
                    if sentence:
                        assistant.live_text = (assistant.current_transcript + " " + sentence).strip()
                        update_stt_status("listening", assistant.live_text)

            def on_utterance_end(dg_self, utterance_end, **kwargs):
                if assistant.live_text.strip():
                    assistant.command_done.set()

            def on_error(dg_self, error, **kwargs):
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
                endpointing=300,
                utterance_end_ms="1500",
                encoding="linear16",
                channels=1,
                sample_rate=self.RATE,
            )

            if not self.dg_connection.start(options):
                return False
            return True

        except Exception as e:
            logger.error(f"Deepgram setup failed: {e}")
            return False

    def _audio_loop(self):
        while self.running:
            try:
                pcm_data = self.stream.read(self.CHUNK, exception_on_overflow=False)

                if not self.is_awake:
                    triggered = False

                    if self.vosk_recognizer.AcceptWaveform(pcm_data):
                        res = json.loads(self.vosk_recognizer.Result())
                        text = res.get("text", "").lower()
                        if any(w in text for w in self.WAKE_WORDS):
                            triggered = True
                    else:
                        partial = json.loads(self.vosk_recognizer.PartialResult())
                        p_text = partial.get("partial", "").lower()
                        if any(w in p_text for w in self.WAKE_WORDS):
                            triggered = True
                            self.vosk_recognizer.Reset()

                    if triggered:
                        logger.info("Wake word 'Jarvis' triggered!")
                        try:
                            from core.voice import tts
                            tts.stop_speaking()
                        except Exception:
                            pass 
                            
                        interrupt.set_interrupt()
                        self.play_wake_sound()

                        if self._setup_deepgram():
                            self.is_awake = True
                            update_stt_status("listening", "")
                else:
                    if self.dg_connection:
                        self.dg_connection.send(pcm_data)

                    if self.command_done.is_set():
                        self.process_final_command()

            except Exception:
                time.sleep(0.01)

    def process_final_command(self):
        if self.dg_connection:
            try:
                self.dg_connection.finish()
            except Exception:
                pass
            finally:
                self.dg_connection = None

        full_command = self.live_text.lower().strip()
        ignore_words = ["", "okay", "okay.", "jarvis", "jarvis.", "thanks", "thank you", "hmm", "haan", "ah", "uh", "theek hai", "hello", "ha"]

        self.is_awake = False
        self.vosk_recognizer.Reset()
        interrupt.clear_interrupt()

        if full_command and full_command not in ignore_words and len(full_command) > 3:
            update_stt_status("understanding")
            self.command_queue.put(full_command)
        else:
            update_stt_status("idle")
            self.command_queue.put("")

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

        return command

    def stop(self):
        self.running = False
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()
        except Exception:
            pass

engine = UnifiedVoiceAssistant()

def start_background_wake_word_listener():
    engine.start()

def listen():
    return engine.get_command()

if __name__ == "__main__":
    try:
        start_background_wake_word_listener()
        while True:
            command = listen()
            if command:
                pass
    except KeyboardInterrupt:
        engine.stop()