import os
import time
import threading
import queue
import struct
import winsound
import pyaudio
import pvporcupine
from datetime import datetime
from dotenv import load_dotenv

from core.logger.logger import logger
from core.voice.stt_status import update_stt_status
from core.voice import interrupt
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

load_dotenv()

PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY", "oLxGUCx6LY/f8Ru4pUzZIattcQ9NLLmzYkDXKB7vao5dn2laj14DIg==")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

if not DEEPGRAM_API_KEY:
    logger.error("DEEPGRAM_API_KEY nahi mili! Please check your .env file.")

deepgram = DeepgramClient(DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY else None
update_stt_status("idle", "")

ACTIVE_CONTEXT_WINDOW = 120  
last_valid_command_time = 0


class UnifiedVoiceAssistant:
    def __init__(self):
        try:
            self.porcupine = pvporcupine.create(
                access_key=PICOVOICE_ACCESS_KEY,
                keywords=['jarvis'],
                sensitivities=[0.40]
            )
        except Exception as e:
            logger.error(f"Porcupine init error: {e}")
            raise

        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=self.porcupine.frame_length
        )

        self.is_awake = False
        self.running = True
        self.command_queue = queue.Queue()

        self.dg_connection = None
        self.current_transcript = ""
        self.live_text = ""
        self.command_done = threading.Event()

    def start(self):
        logger.info("Unified Voice Engine Started (Waiting for 'Jarvis')...")
        self.listen_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.listen_thread.start()

    def play_wake_sound(self):
        try:
            winsound.Beep(2000, 150)
        except:
            pass

    def _setup_deepgram(self):
        """Initialize Deepgram live connection for speech-to-text."""
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
                        logger.info("Speech Final triggered by Deepgram.")
                        assistant.command_done.set()
                else:
                    if sentence:
                        assistant.live_text = (assistant.current_transcript + " " + sentence).strip()
                        update_stt_status("listening", assistant.live_text)

            def on_utterance_end(dg_self, utterance_end, **kwargs):
                logger.info("Utterance End (Silence) detected by Deepgram.")
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
                endpointing=300,
                utterance_end_ms="1500",
                encoding="linear16",
                channels=1,
                sample_rate=16000,
            )

            if not self.dg_connection.start(options):
                logger.error("Failed to connect to Deepgram API")
                return False
            return True

        except Exception as e:
            logger.error(f"Deepgram Setup Error: {e}")
            return False

    def _audio_loop(self):
        from core.voice import tts

        while self.running:
            try:
                pcm_data = self.stream.read(self.porcupine.frame_length, exception_on_overflow=False)

                if not self.is_awake:
                    pcm_unpacked = struct.unpack_from("h" * self.porcupine.frame_length, pcm_data)
                    keyword_index = self.porcupine.process(pcm_unpacked)

                    if keyword_index >= 0:
                        logger.info("WAKE WORD DETECTED!")
                        tts.stop_speaking()
                        interrupt.set_interrupt()
                        self.play_wake_sound()

                        # Start listening immediately – no authentication
                        if self._setup_deepgram():
                            self.is_awake = True
                            update_stt_status("listening", "")
                else:
                    # Active listening: send audio to Deepgram
                    if self.dg_connection:
                        self.dg_connection.send(pcm_data)

                    # If command is complete, process it
                    if self.command_done.is_set():
                        self.process_final_command()

            except Exception as e:
                logger.debug(f"Audio loop error/glitch: {e}")
                time.sleep(0.1)

    def process_final_command(self):
        """Process the final transcribed command."""
        global last_valid_command_time

        if self.dg_connection:
            try:
                self.dg_connection.finish()
            except Exception as e:
                logger.error(f"Error closing Deepgram connection: {e}")
            finally:
                self.dg_connection = None

        full_command = self.live_text.lower().strip()
        ignore_words = ["", "okay", "okay.", "jarvis", "jarvis.", "thanks", "thank you", "hmm", "haan", "ah", "uh", "theek hai", "hello", "ha"]

        if full_command and full_command not in ignore_words and len(full_command) > 3:
            logger.info(f"You said: {full_command}")
            update_stt_status("understanding")
            last_valid_command_time = time.time()
            self.command_queue.put(full_command)
        else:
            logger.info("Silence or garbage noise detected.")
            update_stt_status("idle")
            self.command_queue.put("")

        self.is_awake = False
        interrupt.clear_interrupt()

    def get_command(self, is_retry=False):
        """Retrieve the next command from the queue."""
        global last_valid_command_time

        command = None
        while self.running:
            try:
                command = self.command_queue.get(timeout=0.5)
                break
            except queue.Empty:
                continue

        if not self.running or command is None:
            return ""

        if command == "":
            current_time = time.time()
            time_since_last_cmd = current_time - last_valid_command_time

            # If within active context window, prompt user to speak again
            if last_valid_command_time > 0 and time_since_last_cmd < ACTIVE_CONTEXT_WINDOW and not is_retry:
                from core.voice.tts import speak
                logger.info("Active Context Detected: Prompting user...")
                speak("[thinking] Ji sir? Main sun raha hu.")
                time.sleep(0.5)

                if self._setup_deepgram():
                    self.is_awake = True
                    update_stt_status("listening", "")
                    return self.get_command(is_retry=True)
            return ""

        return command

    def stop(self):
        """Clean shutdown."""
        self.running = False
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()
            self.porcupine.delete()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


# Global engine instance
engine = UnifiedVoiceAssistant()


def start_background_wake_word_listener():
    engine.start()


def listen():
    return engine.get_command()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" JARVIS STT - CLEAN (NO BIOMETRIC AUTH) ")
    print("=" * 60)

    try:
        start_background_wake_word_listener()

        while True:
            command = listen()
            if command:
                print(f"\n FINAL COMMAND CAUGHT: '{command}'\n")
            else:
                print("\n Koi command capture nahi hui (Silence/Noise).\n")

    except KeyboardInterrupt:
        print("\n\n Test mode band kiya jaa raha hai... Goodbye!")
        engine.stop()