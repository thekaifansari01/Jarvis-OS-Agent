import faulthandler
faulthandler.enable()
import os
import sys
import warnings
import ctypes
import logging
import platform
import pygame
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor

os.environ['TOGETHER_NO_BANNER'] = '1'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')
os.system('cls' if os.name == 'nt' else 'clear')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from core.terminal.jarvis_terminal import init_terminal
init_terminal()

from core.brain.Memory.Memory import ContextMemory
from core.voice import stt, tts, interrupt
from core.terminal.tray_manager import start_tray_icon
from core.voice.stt_status import hide_stt_popup
from core.utils.ProcessManager import proc_manager
from Proactive.proactive_agent import start_proactive_agent

from core.main.BackgroundServices import start_agent_panel, start_stt_popup, start_baileys_server, stop_all_services
from core.main.CommandHandler import main_command_processor, is_jarvis_busy
from core.main.HotKeyManager import setup_hotkeys
from core.main.ServiceWatchdog import start_watchdog, stop_watchdog

_is_running = True

def signal_handler(signum, frame):
    global _is_running
    _is_running = False
    logging.info("Interrupt signal received. Initiating graceful shutdown.")
    try:
        stop_watchdog()
        stop_all_services()
        proc_manager.cleanup()
    except Exception as e:
        logging.error(f"Error during signal cleanup: {e}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main() -> None:
    global _is_running

    args = [arg.lower() for arg in sys.argv[1:]]
    is_dev_mode = "test_jarvis" in args
    use_tray = "system_tray=no" not in args

    for arg in args:
        if arg.startswith("voice="):
            forced_tts = arg.split("=", 1)[1].strip()
            break

    if use_tray:
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception as e:
            logging.error(f"Failed to hide console window: {e}")

    icon_path = None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    possible_icon_paths = [
        os.path.join(base_dir, "Data", "icons", "jarvis_icon.png"),
        os.path.join(base_dir, "jarvis_icon.png"),
        os.path.join(base_dir, "assets", "jarvis_icon.png")
    ]
    for p in possible_icon_paths:
        if os.path.exists(p):
            icon_path = p
            break

    if use_tray and icon_path:
        try:
            tray_thread = threading.Thread(target=start_tray_icon, args=(icon_path,), daemon=True)
            tray_thread.start()
        except Exception as e:
            logging.error(f"Failed to start tray icon: {e}")

    try:
        from core.ui.agent_status import reset_agent_status
        reset_agent_status()
    except Exception:
        pass

    start_agent_panel()
    start_stt_popup()
    start_baileys_server()
    start_watchdog()

    if not is_dev_mode:
        time.sleep(1)

    try:
        memory = ContextMemory()
    except Exception as e:
        logging.warning(f"Failed to initialize ContextMemory, using fallback: {e}")
        class FakeMemory:
            def get_relevant_context(self, text): return ""
            def add_message(self, role, text, metadata=None): pass
            preferences = {"likes": []}
            ephemeral = {}
            def get_and_clear_feedback(self): return None
            def add_live_feedback(self, cmd): pass
        memory = FakeMemory()

    try:
        start_proactive_agent(memory, is_jarvis_busy)
    except Exception as e:
        logging.error(f"Failed to start proactive agent: {e}")

    mode = "TEXT" if is_dev_mode else "VOICE"

    if mode == "VOICE":
        try:
            stt.start_background_wake_word_listener()
        except Exception as e:
            logging.error(f"Failed to start wake word listener: {e}")

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            setup_hotkeys(executor, memory)

            while _is_running:
                try:
                    command = ""
                    if mode == "TEXT":
                        try:
                            command = input("\n❯ ").strip()
                        except EOFError:
                            break
                    else:
                        command = stt.listen()
                        if not command:
                            continue

                    if command and command.lower() in ["exit", "quit", "stop", "bye"]:
                        _is_running = False
                        logging.info("Exit command received.")
                        try:
                            tts.stop_speaking()
                        except Exception:
                            pass
                        break

                    if command:
                        if is_jarvis_busy() and hasattr(memory, 'add_live_feedback'):
                            try:
                                memory.add_live_feedback(command)
                                interrupt.clear_interrupt()
                            except Exception as e:
                                logging.error(f"Failed to add live feedback: {e}")
                        else:
                            try:
                                hide_stt_popup()
                            except Exception:
                                pass
                            executor.submit(main_command_processor, command, executor, memory)
                            interrupt.clear_interrupt()

                except KeyboardInterrupt:
                    _is_running = False
                    logging.info("Keyboard interrupt received.")
                    break
                except Exception as e:
                    logging.error(f"Error in main event loop: {e}")
                    continue
    finally:
        logging.info("Starting shutdown sequence.")
        try:
            tts.cleanup_temp()
            pygame.quit()
        except Exception as e:
            logging.error(f"Error cleaning up TTS/Pygame: {e}")
        
        stop_watchdog()
        stop_all_services()
        
        try:
            proc_manager.cleanup()
        except Exception as e:
            logging.error(f"Error cleaning up process manager: {e}")
            
        logging.info("Shutdown sequence complete.")

if __name__ == "__main__":
    main()