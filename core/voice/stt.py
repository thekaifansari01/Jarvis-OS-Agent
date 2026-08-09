import os
import time
import threading
import queue
import winsound
import pyaudio
import json
import struct
import math
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
    logger.error("❌ [bold red]DEEPGRAM_API_KEY missing in .env file![/bold red]")
else:
    logger.info("🔑 [green]Deepgram API Key found.[/green]")

deepgram = DeepgramClient(DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY else None
update_stt_status("idle", "")

class UnifiedVoiceAssistant:
    def __init__(self):
        logger.info("🎤 [bold cyan]Initializing Unified Voice Assistant...[/bold cyan]")
        self.CHUNK = 2048
        self.RATE = 16000
        self.MIN_RMS_THRESHOLD = 800
        self.WAKE_WORDS = ["jarvis", "hey jarvis"]

        model_path = "Data/model/vosk-model-small"
        if not os.path.exists(model_path):
            logger.error(f"📁 [bold red]Vosk model folder not found at:[/bold red] {model_path}")
            raise FileNotFoundError(f"Vosk model not found at '{model_path}'.")
        
        try:
            logger.info("⏳ [cyan]Loading Vosk wake-word model...[/cyan]")
            self.vosk_model = VoskModel(model_path)
            grammar_list = self.WAKE_WORDS + ["[unk]", "hello", "hi", "computer"]
            grammar = json.dumps(grammar_list)
            self.vosk_recognizer = KaldiRecognizer(self.vosk_model, self.RATE, grammar)
            logger.info("🧠 [bold green]Vosk model loaded successfully.[/bold green]")
        except Exception as e:
            logger.error(f"❌ [bold red]Failed to initialize Vosk model:[/bold red] {e}")
            raise

        try:
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )
            logger.info("🎛️ [bold green]Audio stream opened successfully.[/bold green]")
        except Exception as e:
            logger.error(f"❌ [bold red]Failed to open audio stream:[/bold red] {e}")
            raise

        self.is_awake = False
        self.running = True
        self.command_queue = queue.Queue()

        self.dg_connection = None
        self.current_transcript = ""
        self.live_text = ""
        self.command_done = threading.Event()
        self.connection_established = False
        logger.info("✅ [bold green]Unified Voice Assistant initialized and ready.[/bold green]")

    def start(self):
        logger.info("▶️ [bold cyan]Starting background wake-word listener...[/bold cyan]")
        self.listen_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.listen_thread.start()

    def play_wake_sound(self):
        pass

    def _get_rms(self, pcm_data):
        try:
            count = len(pcm_data) // 2
            shorts = struct.unpack(f"{count}h", pcm_data)
            sum_squares = sum(s**2 for s in shorts)
            return math.sqrt(sum_squares / count)
        except Exception:
            return 0

    def _setup_deepgram(self):
        logger.info("🌐 [cyan]Setting up Deepgram Live Connection...[/cyan]")
        self.current_transcript = ""
        self.live_text = ""
        self.command_done.clear()
        assistant = self

        try:
            self.dg_connection = deepgram.listen.live.v("1")

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
                logger.error(f"❌ [bold red]Deepgram Error:[/bold red] {error}")
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
                endpointing=600,
                utterance_end_ms="1000",
                encoding="linear16",
                channels=1,
                sample_rate=self.RATE,
            )

            if not self.dg_connection.start(options):
                logger.warning("⚠️ [bold yellow]Failed to start Deepgram connection.[/bold yellow]")
                return False
            
            logger.info("🚀 [bold green]Deepgram live connection established successfully![/bold green]")
            return True

        except Exception as e:
            logger.error(f"❌ [bold red]Deepgram setup failed:[/bold red] {e}")
            return False

    def _check_wake_word(self, text):
        words = text.lower().split()
        for phrase in self.WAKE_WORDS:
            phrase_words = phrase.split()
            if len(phrase_words) == 1:
                if phrase_words[0] in words:
                    return True
            else:
                if phrase in text.lower():
                    return True
        return False

    def _audio_loop(self):
        logger.info("🎧 [cyan]Listening for wake word...[/cyan]")
        while self.running:
            try:
                pcm_data = self.stream.read(self.CHUNK, exception_on_overflow=False)

                if not self.is_awake:
                    rms = self._get_rms(pcm_data)
                    triggered = False

                    if self.vosk_recognizer.AcceptWaveform(pcm_data):
                        res = json.loads(self.vosk_recognizer.Result())
                        text = res.get("text", "")
                        
                        if self._check_wake_word(text) and rms >= self.MIN_RMS_THRESHOLD:
                            logger.info(f"🔔 [bold yellow]Wake word detected (Final):[/bold yellow] '{text}' [cyan](RMS: {rms:.2f})[/cyan]")
                            triggered = True
                    else:
                        partial = json.loads(self.vosk_recognizer.PartialResult())
                        p_text = partial.get("partial", "").strip()
                        
                        if p_text in self.WAKE_WORDS and rms >= (self.MIN_RMS_THRESHOLD + 200):
                            logger.info(f"⏳ [bold yellow]Wake word detected (Partial):[/bold yellow] '{p_text}' [cyan](RMS: {rms:.2f})[/cyan]")
                            triggered = True
                            self.vosk_recognizer.Reset()

                    if triggered:
                        try:
                            from core.voice import tts
                            tts.stop_speaking()
                            logger.info("🛑 [cyan]Stopped TTS playback due to wake word.[/cyan]")
                        except Exception:
                            pass 
                            
                        interrupt.set_interrupt()
                        self.play_wake_sound()

                        self.current_transcript = ""
                        self.live_text = ""
                        self.command_done.clear()

                        if not self.connection_established or self.dg_connection is None:
                            if self._setup_deepgram():
                                self.connection_established = True
                            else:
                                self.connection_established = False
                                logger.warning("⚠️ [yellow]Retrying wake word detection due to Deepgram failure.[/yellow]")
                                continue

                        self.is_awake = True
                        update_stt_status("listening", "")
                        logger.info("👂 [bold green]System Awake. Listening for command...[/bold green]")
                else:
                    if self.dg_connection:
                        try:
                            self.dg_connection.send(pcm_data)
                        except Exception as e:
                            logger.error(f"⚠️ [bold red]Lost connection to Deepgram while streaming:[/bold red] {e}")
                            self.dg_connection = None
                            self.connection_established = False
                            self.is_awake = False
                            logger.info("🎧 [cyan]Reverting to wake word detection mode...[/cyan]")
                            continue

                    if self.command_done.is_set():
                        self.process_final_command()

            except Exception:
                time.sleep(0.01)

    def process_final_command(self):
        full_command = self.live_text.lower().strip()
        ignore_words = ["", "okay", "okay.", "jarvis", "jarvis.", "thanks", "thank you", "hmm", "haan", "ah", "uh", "theek hai", "hello", "ha"]

        self.is_awake = False
        self.vosk_recognizer.Reset()
        interrupt.clear_interrupt()

        try:
            if self.dg_connection:
                self.dg_connection.finish()
                logger.info("🔌 [cyan]Deepgram connection closed gracefully.[/cyan]")
        except Exception as e:
            logger.warning(f"⚠️ [yellow]Error closing Deepgram connection:[/yellow] {e}")
        finally:
            self.dg_connection = None
            self.connection_established = False

        if full_command and full_command not in ignore_words and len(full_command) > 3:
            logger.info(f"🗣️ [bold green]Final Command Received:[/bold green] '{full_command}'")
            update_stt_status("understanding")
            self.command_queue.put(full_command)
        else:
            if full_command:
                logger.info(f"🛑 [yellow]Command ignored (too short or in ignore list):[/yellow] '{full_command}'")
            else:
                logger.info("🛑 [yellow]No valid command detected. Returning to idle.[/yellow]")
            
            update_stt_status("idle")
            self.command_queue.put("")
        
        logger.info("🎧 [cyan]Listening for wake word...[/cyan]")

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
        logger.info("🛑 [bold red]Stopping Unified Voice Assistant...[/bold red]")
        self.running = False
        try:
            if self.dg_connection:
                self.dg_connection.finish()
        except Exception:
            pass
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()
            logger.info("🎛️ [green]Audio stream closed.[/green]")
        except Exception as e:
            logger.error(f"⚠️ [red]Error closing audio stream:[/red] {e}")
        logger.info("👋 [bold cyan]Voice Assistant stopped successfully.[/bold cyan]")

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
        logger.warning("\n⚠️ [bold yellow]KeyboardInterrupt detected![/bold yellow]")
        engine.stop()