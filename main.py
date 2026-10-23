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
from ctypes import wintypes
import atexit

os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['OMP_NUM_THREADS'] = '4'
os.environ['MKL_NUM_THREADS'] = '4'
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['POSTHOG_DISABLED'] = '1'
os.environ['TOGETHER_NO_BANNER'] = '1'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(write_through=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(write_through=True)

from core.logger.logger import logger
from terminalCommands import handle_cli_commands, create_lock_file, remove_lock_file, is_jarvis_running

_is_running = True
_shutdown_lock = threading.Lock()
_shutdown_started = False
_console_hwnd = None
_tray_icon = None
_executor = None
_console_ctrl_handler_ref = None

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
GWL_STYLE = -16
WS_MAXIMIZEBOX = 0x00010000
WS_THICKFRAME = 0x00040000
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
SC_SIZE = 0xF000
SC_MAXIMIZE = 0xF030
MF_BYCOMMAND = 0x00000000


class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [
        ("Left", ctypes.c_short),
        ("Top", ctypes.c_short),
        ("Right", ctypes.c_short),
        ("Bottom", ctypes.c_short),
    ]


def get_console_hwnd():
    global _console_hwnd
    if platform.system() != "Windows":
        return None
    if _console_hwnd and ctypes.windll.user32.IsWindow(_console_hwnd):
        return _console_hwnd
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd or not user32.IsWindowVisible(hwnd):
            fg_hwnd = user32.GetForegroundWindow()
            if fg_hwnd:
                hwnd = fg_hwnd
        _console_hwnd = hwnd
        return hwnd
    except Exception:
        return None


def disable_quickedit():
    if platform.system() == "Windows":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-10)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                mode.value &= ~0x0040
                mode.value |= 0x0080
                kernel32.SetConsoleMode(handle, mode)
        except Exception:
            pass


def lock_console_window(cols=96, rows=28, width_px=860, height_px=540, buffer_rows=5000):
    if platform.system() != "Windows":
        return
    disable_quickedit()

    is_windows_terminal = bool(os.environ.get("WT_SESSION"))

    try:
        kernel32 = ctypes.windll.kernel32
        h_out = kernel32.GetStdHandle(-11)
        if h_out and h_out != -1:
            # Step 1: window ko minimum karo
            min_rect = SMALL_RECT(0, 0, 1, 1)
            kernel32.SetConsoleWindowInfo(h_out, True, ctypes.byref(min_rect))

            # Step 2: buffer bada karo (sirf legacy conhost me kaam karega)
            if not is_windows_terminal:
                buf_size = COORD(cols, max(buffer_rows, rows))
                ok = kernel32.SetConsoleScreenBufferSize(h_out, buf_size)
                if not ok:
                    logger.warning("SetConsoleScreenBufferSize failed — scroll disabled")

            # Step 3: window ko desired size pe lao
            win_rect = SMALL_RECT(0, 0, cols - 1, rows - 1)
            kernel32.SetConsoleWindowInfo(h_out, True, ctypes.byref(win_rect))
    except Exception as e:
        logger.warning(f"Console resize failed: {e}")

    try:
        sys.stdout.write(f"\033[8;{rows};{cols}t")
        sys.stdout.flush()
    except Exception:
        pass

    try:
        user32 = ctypes.windll.user32
        hwnd = get_console_hwnd()
        if hwnd:
            if user32.IsZoomed(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~WS_MAXIMIZEBOX
            style &= ~WS_THICKFRAME
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            hmenu = user32.GetSystemMenu(hwnd, False)
            if hmenu:
                user32.DeleteMenu(hmenu, SC_SIZE, MF_BYCOMMAND)
                user32.DeleteMenu(hmenu, SC_MAXIMIZE, MF_BYCOMMAND)
            user32.SetWindowPos(
                hwnd, 0, rect.left, rect.top,
                width_px, height_px,
                SWP_NOZORDER | SWP_FRAMECHANGED
            )
    except Exception:
        pass


def restore_console():
    if platform.system() == "Windows":
        try:
            hwnd = get_console_hwnd()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def set_terminal_title(title="Jarvis"):
    try:
        if platform.system() == "Windows":
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        else:
            sys.stdout.write(f"\033]0;{title}\007")
            sys.stdout.flush()
    except Exception:
        pass


def render_banner(mic_available=False, no_wake=False, state="ONLINE & READY"):
    os.system('cls' if os.name == 'nt' else 'clear')
    voice_mode = "VOICE ENABLED" if (mic_available and not no_wake) else "TEXT-ONLY MODE"
    print(r"""
         ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
         ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
         ██║███████║██████╔╝██║   ██║██║███████╗
    ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
    ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
     ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝""")
    print("  " + "═" * 88)
    print(f"   STATUS : {state:<22} │ INPUT : {voice_mode:<18} │ HOTKEY : Ctrl+Shift+J")
    print("   INDEXER: http://127.0.0.1:8080  │ MOBILE: http://127.0.0.1:8090  │ EXIT   : Ctrl+C / Close")
    print("  " + "═" * 88 + "\n")


def shutdown_jarvis(reason="Shutdown signal received", exit_code=0):
    global _is_running, _shutdown_started, _tray_icon, _executor
    with _shutdown_lock:
        if _shutdown_started:
            return
        _shutdown_started = True
        _is_running = False

    restore_console()
    logger.info(f"{reason}. Initiating graceful shutdown...")

    try:
        from core.utils.shutdown import set_shutdown
        set_shutdown()
    except Exception as e:
        logger.error(f"Error setting shutdown flag: {e}")

    try:
        remove_lock_file()
    except Exception as e:
        logger.error(f"Error removing lock file: {e}")

    if _tray_icon is not None:
        try:
            _tray_icon.stop()
        except Exception:
            pass
        _tray_icon = None

    try:
        from core.brain.Memory.LifetimeMemory import ltm_engine
        ltm_engine._save_graph()
        logger.info("LTM Graph saved successfully.")
    except Exception as e:
        logger.error(f"Error saving LTM graph: {e}")

    try:
        from core.brain.Memory.BehavioralEngine import behavioral_pattern_engine
        behavioral_pattern_engine.shutdown()
        logger.info("Behavioral Pattern Engine state saved successfully.")
    except Exception as e:
        logger.error(f"Error saving Behavioral Pattern Engine state: {e}")

    if _executor is not None:
        try:
            _executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            try:
                _executor.shutdown(wait=False)
            except Exception:
                pass
        except Exception:
            pass
        _executor = None

    try:
        from core.voice import tts
        try:
            tts.stop_speaking()
        except Exception:
            pass
        tts.cleanup_temp()
    except Exception as e:
        logger.error(f"Error cleaning up TTS: {e}")

    try:
        import pygame
        pygame.quit()
    except Exception:
        pass

    try:
        from core.main.ServiceWatchdog import stop_watchdog
        stop_watchdog()
    except Exception as e:
        logger.error(f"Error stopping watchdog: {e}")

    try:
        from core.main.BackgroundServices import stop_all_services
        stop_all_services()
    except Exception as e:
        logger.error(f"Error stopping background services: {e}")

    try:
        from core.utils.ProcessManager import proc_manager
        proc_manager.cleanup()
    except Exception as e:
        logger.error(f"Error cleaning up process manager: {e}")

    logger.info("Shutdown sequence complete.")
    os._exit(exit_code)


def signal_handler(signum, frame):
    shutdown_jarvis(reason=f"Signal {signum} received", exit_code=0)


def register_shutdown_handlers():
    global _console_ctrl_handler_ref
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal_handler)
    atexit.register(lambda: shutdown_jarvis(reason="Process exit triggered", exit_code=0))

    if platform.system() == "Windows":
        try:
            HANDLER_ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.DWORD)

            def _win_ctrl_handler(ctrl_type):
                if ctrl_type in (0, 1, 2, 5, 6):
                    shutdown_jarvis(reason=f"Windows console close event ({ctrl_type})", exit_code=0)
                    return True
                return False

            _console_ctrl_handler_ref = HANDLER_ROUTINE(_win_ctrl_handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_ctrl_handler_ref, True)
        except Exception as e:
            logger.error(f"Failed to register Windows console handler: {e}")


def start_tray_icon():
    global _tray_icon
    try:
        import pystray
        from PIL import Image
    except ImportError:
        logger.error("pystray or PIL not installed. Run 'pip install pystray pillow' for system tray feature.")
        return

    hwnd = get_console_hwnd()

    def show_window(icon, item):
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            lock_console_window()

    def exit_app(icon, item):
        shutdown_jarvis(reason="System tray exit requested", exit_code=0)

    menu = pystray.Menu(
        pystray.MenuItem('Open Jarvis', show_window, default=True),
        pystray.MenuItem('Exit Jarvis', exit_app)
    )

    icon_path = os.path.join(PROJECT_ROOT, "Data", "icons", "jarvis_icon.png")
    try:
        image = Image.open(icon_path)
    except Exception:
        image = Image.new('RGB', (64, 64), color=(0, 0, 0))

    _tray_icon = pystray.Icon("Jarvis", image, "Jarvis", menu)

    def monitor():
        while _is_running:
            try:
                if hwnd and ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
            except Exception:
                pass
            time.sleep(0.25)

    threading.Thread(target=monitor, daemon=True).start()
    _tray_icon.run()


def run_jarvis():
    global _is_running, _executor

    register_shutdown_handlers()
    render_banner(mic_available=False, no_wake=True, state="BOOTING SYSTEMS...")

    try:
        import pygame
        from concurrent.futures import ThreadPoolExecutor
        from core.brain.Memory.Memory import ContextMemory
        from core.voice import stt, tts, interrupt
        from core.voice.stt_status import hide_stt_popup
        from Proactive.proactive_agent import start_proactive_agent
        from core.main.BackgroundServices import (
            start_agent_panel,
            start_stt_popup,
            start_rag_engine,
            start_baileys_server,
            start_mobile_bridge,
            start_telegram_remote_service
        )
        from core.main.CommandHandler import main_command_processor, is_jarvis_busy
        from core.main.HotKeyManager import setup_hotkeys
        from core.main.ServiceWatchdog import start_watchdog
        from core.main.TelegramRemoteBot import set_telegram_remote_context
    except ImportError as e:
        logger.error(f"Critical module missing: {e}. Please ensure all dependencies are installed.")
        remove_lock_file()
        sys.exit(1)

    args = [arg.lower() for arg in sys.argv[1:]]
    no_wake = "no_wake" in args

    mic_available = getattr(stt.engine, 'mic_available', False)
    if mic_available:
        logger.info("Microphone detected — voice input ENABLED.")
    else:
        logger.warning("Microphone NOT detected — voice input DISABLED. Jarvis running in text-only mode.")

    try:
        from core.ui.agent_status import reset_agent_status
        reset_agent_status()
    except Exception as e:
        logger.error(f"Error resetting agent status: {e}")

    start_agent_panel()
    start_stt_popup()
    start_baileys_server()
    start_watchdog()
    start_mobile_bridge()

    def start_gui_warmup_background():
        try:
            from tools.SystemTools.GuiTools import warmup_gui_system
            warmup_gui_system()
        except Exception as e:
            logger.warning(f"GUI system warmup failed: {e}")

    threading.Thread(target=start_gui_warmup_background, daemon=True).start()

    try:
        from core.brain.Memory.BehavioralEngine import behavioral_pattern_engine
    except Exception as e:
        logger.error(f"Error initializing Behavioral Pattern Engine: {e}")

    def start_rag_background():
        try:
            start_rag_engine()
        except Exception as e:
            logger.error(f"RAG engine startup failed: {e}")

    threading.Thread(target=start_rag_background, daemon=True).start()

    try:
        memory = ContextMemory()
    except Exception as e:
        logger.warning(f"Failed to initialize ContextMemory, using fallback: {e}")

        class FakeMemory:
            def get_fast_history_context(self): return "No recent conversation."
            def get_agentic_fast_context(self): return "<Recent_Context>\nNo recent conversation.\n</Recent_Context>"
            def get_ephemeral_context(self, mode="agentic", current_command=""): return ""
            def get_static_ephemeral_context(self, current_command=""): return ""
            def get_dynamic_ephemeral_context(self, current_command=""): return ""
            def add_message(self, role, text, metadata=None): pass
            preferences = {"likes": []}
            ephemeral = {}
            def set_pending_confirmation(self, task_data=None, ttl_seconds=90): pass
            def clear_pending_confirmation(self): pass
            def consume_pending_confirmation(self): return None
            def consume_silent_flag(self): return False
            def set_last_artifact(self, key, file_path, ttl_seconds=600): pass
            def set_ml_ephemeral(self, ml_payload, ttl_seconds=600): pass
            def get_and_clear_feedback(self): return ""
            def add_live_feedback(self, cmd): pass
            def catchup_summaries(self): pass

        memory = FakeMemory()

    def start_memory_catchup():
        try:
            if hasattr(memory, "catchup_summaries"):
                memory.catchup_summaries()
        except Exception as e:
            logger.error(f"Memory catch-up failed at startup: {e}")

    threading.Thread(target=start_memory_catchup, daemon=True).start()

    def start_proactive_background():
        try:
            start_proactive_agent(memory, is_jarvis_busy)
        except Exception as e:
            logger.error(f"Failed to start proactive agent: {e}")

    threading.Thread(target=start_proactive_background, daemon=True).start()

    if not no_wake and mic_available:
        try:
            stt.start_background_wake_word_listener()
        except Exception as e:
            logger.error(f"Failed to start wake word listener: {e}")
    elif not mic_available:
        logger.warning("Skipping wake word listener — microphone not available.")

    render_banner(mic_available=mic_available, no_wake=no_wake, state="ONLINE & READY")
    lock_console_window()

    _executor = ThreadPoolExecutor(max_workers=5)
    try:
        setup_hotkeys(_executor, memory)
        set_telegram_remote_context(_executor, memory)
        start_telegram_remote_service()

        if no_wake or not mic_available:
            logger.info("Jarvis running in background/text-only mode. Waiting for shutdown signal...")
            while _is_running:
                time.sleep(0.5)
        else:
            while _is_running:
                try:
                    command = stt.listen()
                    if not _is_running:
                        break
                    if not command:
                        continue
                    if command.strip().lower() in ["exit", "quit", "stop", "bye"]:
                        logger.info("Exit command received.")
                        break
                    if is_jarvis_busy() and hasattr(memory, 'add_live_feedback'):
                        try:
                            memory.add_live_feedback(command)
                            interrupt.clear_interrupt()
                        except Exception as e:
                            logger.error(f"Failed to add live feedback: {e}")
                    else:
                        try:
                            hide_stt_popup()
                        except Exception as e:
                            logger.error(f"Error hiding STT popup: {e}")
                        if _executor is not None and _is_running:
                            _executor.submit(main_command_processor, command, _executor, memory)
                        interrupt.clear_interrupt()
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received.")
                    break
                except Exception as e:
                    logger.error(f"Error in main event loop: {e}")
                    continue
    finally:
        shutdown_jarvis(reason="Main event loop ended", exit_code=0)


def main() -> None:
    get_console_hwnd()
    set_terminal_title("Jarvis")

    try:
        if handle_cli_commands():
            sys.exit(0)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user.")
        sys.exit(0)

    if is_jarvis_running():
        logger.error("Jarvis is ALREADY running in another terminal window!")
        logger.error("Please close the existing Jarvis instance before starting a new one.")
        sys.exit(1)

    lock_console_window()
    create_lock_file()

    if platform.system() == "Windows":
        try:
            import pystray
            from PIL import Image
            threading.Thread(target=start_tray_icon, daemon=True).start()
        except ImportError:
            pass

    run_jarvis()


if __name__ == "__main__":
    main()