import faulthandler
faulthandler.enable()
import os
import sys
import platform
import threading
import warnings
import logging
import signal
import time
import ctypes

os.environ['PYTHONUNBUFFERED'] = '1'

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(write_through=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(write_through=True)

def disable_quickedit():
    if platform.system() == "Windows":
        try:
            kernel32 = ctypes.windll.kernel32
            STD_INPUT_HANDLE = -10
            ENABLE_QUICK_EDIT_MODE = 0x0040
            ENABLE_EXTENDED_FLAGS = 0x0080
            handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            mode.value &= ~ENABLE_QUICK_EDIT_MODE
            mode.value |= ENABLE_EXTENDED_FLAGS
            kernel32.SetConsoleMode(handle, mode)
        except Exception:
            pass

disable_quickedit()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ['TOGETHER_NO_BANNER'] = '1'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from terminalCommands import handle_cli_commands, create_lock_file, remove_lock_file, is_jarvis_running

_is_running = True

def signal_handler(signum, frame):
    global _is_running
    _is_running = False
    logging.info("Interrupt signal received. Initiating graceful shutdown.")
    try:
        remove_lock_file()
        from core.main.ServiceWatchdog import stop_watchdog
        from core.main.BackgroundServices import stop_all_services
        from core.utils.ProcessManager import proc_manager
        stop_watchdog()
        stop_all_services()
        proc_manager.cleanup()
    except Exception as e:
        logging.error(f"Error during signal cleanup: {e}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def set_terminal_title(title="Jarvis"):
    try:
        if platform.system() == "Windows":
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        else:
            sys.stdout.write(f"\033]0;{title}\007")
            sys.stdout.flush()
    except Exception:
        pass

def main() -> None:
    global _is_running

    set_terminal_title("Jarvis")

    if handle_cli_commands():
        sys.exit(0)

    if is_jarvis_running():
        print("\n❌ [ERROR] Jarvis is ALREADY running in another terminal window!")
        print("⚠️  Please close the existing Jarvis instance before starting a new one.\n")
        sys.exit(1)

    create_lock_file()

    import pygame
    from concurrent.futures import ThreadPoolExecutor
    from core.brain.Memory.Memory import ContextMemory
    from core.voice import stt, tts, interrupt
    from core.voice.stt_status import hide_stt_popup
    from core.utils.ProcessManager import proc_manager
    from Proactive.proactive_agent import start_proactive_agent
    from core.main.BackgroundServices import start_agent_panel, start_stt_popup, start_rag_engine, start_baileys_server, stop_all_services
    from core.main.CommandHandler import main_command_processor, is_jarvis_busy
    from core.main.HotKeyManager import setup_hotkeys
    from core.main.ServiceWatchdog import start_watchdog, stop_watchdog

    args = [arg.lower() for arg in sys.argv[1:]]
    is_dev_mode = "test_jarvis" in args
    no_wake = "no_wake" in args

    try:
        from core.ui.agent_status import reset_agent_status
        reset_agent_status()
    except Exception:
        pass

    start_agent_panel()
    start_stt_popup()
    start_baileys_server()
    start_watchdog()

    def start_rag_background():
        try:
            start_rag_engine()
        except Exception as e:
            logging.error(f"RAG engine startup failed: {e}")

    threading.Thread(target=start_rag_background, daemon=True).start()

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

    def start_proactive_background():
        try:
            start_proactive_agent(memory, is_jarvis_busy)
        except Exception as e:
            logging.error(f"Failed to start proactive agent: {e}")

    threading.Thread(target=start_proactive_background, daemon=True).start()

    if not no_wake:
        try:
            stt.start_background_wake_word_listener()
        except Exception as e:
            logging.error(f"Failed to start wake word listener: {e}")

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            setup_hotkeys(executor, memory)

            if no_wake:
                while _is_running:
                    time.sleep(1)
            else:
                while _is_running:
                    try:
                        command = stt.listen()
                        if not command:
                            continue

                        if command.lower() in ["exit", "quit", "stop", "bye"]:
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

        remove_lock_file()
        stop_watchdog()
        stop_all_services()

        try:
            proc_manager.cleanup()
        except Exception as e:
            logging.error(f"Error cleaning up process manager: {e}")

        logging.info("Shutdown sequence complete.")

if __name__ == "__main__":
    main()