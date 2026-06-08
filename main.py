import os
import sys
import keyboard
import warnings
import subprocess
import threading
import time
import ctypes
import logging
import asyncio
import platform
import pygame
import signal
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
os.environ['TOGETHER_NO_BANNER'] = '1'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')
os.system('cls' if os.name == 'nt' else 'clear')
from core.terminal.jarvis_terminal import init_terminal
init_terminal()
from core.brain.Processor.Processor import process_command
from core.brain.executor import execute_actions
from core.brain.memory import ContextMemory
from core.voice import stt, tts
from tools.OpenCloseApps.open_any import start_background_cache_builder
from core.terminal.tray_manager import start_tray_icon
from core.voice.stt_status import hide_stt_popup, exit_stt_popup
from core.voice import interrupt
from core.utils.ProcessManager import proc_manager

_is_running = True
_panel_process = None
_stt_popup_process = None

_is_busy = False
_is_popup_open = False  

def signal_handler(signum, frame):
    logging.info(f"Received signal {signum}, cleaning up...")
    proc_manager.cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def start_agent_panel():
    global _panel_process
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        panel_script = os.path.join(base_dir, "core", "ui", "agent_panel.py")
        if os.path.exists(panel_script):
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            _panel_process = proc_manager.spawn(
                [sys.executable, panel_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            logging.info("✅ Agent Panel started")
        else:
            logging.warning(f"Agent panel not found")
    except Exception as e:
        logging.warning(f"Could not start agent panel: {e}")

def stop_agent_panel():
    global _panel_process
    if _panel_process:
        try:
            proc_manager.kill_process_tree(_panel_process.pid)
            _panel_process.wait(timeout=2)
        except:
            pass
        _panel_process = None
        logging.info("🛑 Agent Panel stopped")

def start_stt_popup():
    global _stt_popup_process
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        popup_script = os.path.join(base_dir, "core", "ui", "stt_popup.py")
        
        if os.path.exists(popup_script):
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            _stt_popup_process = proc_manager.spawn(
                [sys.executable, popup_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            logging.info(f"🎙️ STT Popup UI started from {popup_script}")
        else:
            logging.warning(f"STT popup script not found at {popup_script}")
    except Exception as e:
        logging.warning(f"Could not start STT popup: {e}")

def stop_stt_popup():
    global _stt_popup_process
    logging.info("🛑 Sending exit signal to STT Popup...")
    try:
        exit_stt_popup()
    except:
        pass
    
    if _stt_popup_process:
        try:
            proc_manager.kill_process_tree(_stt_popup_process.pid)
            _stt_popup_process.wait(timeout=2)
        except:
            pass
        _stt_popup_process = None
        logging.info("🛑 STT Popup UI stopped")

def main_command_processor(command: str, executor: ThreadPoolExecutor, memory: ContextMemory) -> None:
    global _is_busy
    _is_busy = True  
    
    try:
        raw = command.strip() if command else ""
        if not raw:
            return
        
        if interrupt.is_interrupted():
            logging.info("⏸️ Command interrupted by user (wake word during processing).")
            interrupt.clear_interrupt()
            return
        
        result = process_command(raw, memory_instance=memory)
        
        execute_actions(result, executor)
        if 'response' not in result:
            result['response'] = "Action executed."
            
        metadata = result.get('metadata', {})
   
        if not metadata:
            apps_opened = result.get('apps_to_open', [])
            apps_closed = result.get('apps_to_close', [])
            sys_events = []

            if result.get('system_action'):
                sys_events.append(f"System Action: {result['system_action']}")
            if result.get('urls_to_open'):
                sys_events.append(f"Opened URLs: {', '.join(result['urls_to_open'])}")
            if result.get('workspace_file_to_open'):
                sys_events.append(f"Opened Workspace File: {result['workspace_file_to_open']}")

            if apps_opened or apps_closed or sys_events:
                metadata = {
                    "apps_opened": apps_opened,
                    "apps_closed": apps_closed,
                    "system_events": sys_events,
                    "files_touched": [] 
                }
              
        try:
            
            memory.add_message("USER", raw)
            
            memory.add_message("JARVIS", result.get('response', ''), metadata=metadata if metadata else None)
        except Exception as e:
            logging.warning(f"Memory Update Failed: {e}")
            
        if result.get("response"):
            time.sleep(0.1)
            
    except Exception as e:
        logging.error(f"❌ CRASH IN COMMAND PROCESSOR: {e}", exc_info=True)
        
    finally:
        _is_busy = False  
        
        if memory and hasattr(memory, 'get_and_clear_feedback'):
            cleared_feedback = memory.get_and_clear_feedback()
            if cleared_feedback:
                logging.info(f"🗑️ Flushed hanging live feedback after task completion: {cleared_feedback}")

def main() -> None:
    global _is_running
    global _is_busy
    global _is_popup_open 

    args = [arg.lower() for arg in sys.argv[1:]]
    
    is_dev_mode = "test_jarvis" in args
    use_tray = "system_tray=no" not in args

    forced_tts = None
    for arg in args:
        if arg.startswith("voice="):
            forced_tts = arg.split("=", 1)[1].strip()
            if forced_tts == "edge_tts":
                logging.info("🔊 TTS engine is natively using edge_tts")
            else:
                logging.warning(f"Unknown or unsupported voice engine: {forced_tts}. Ignoring. Valid: edge_tts")
            break

    if use_tray:
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except:
            pass

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
            if use_tray:
                logging.info(f"✅ Found tray icon: {p}")
            break
    if not icon_path and use_tray:
        logging.warning("⚠️ Custom icon not found, using default blue circle")

    if use_tray:
        try:
            tray_thread = threading.Thread(target=start_tray_icon, args=(icon_path,), daemon=True)
            tray_thread.start()
            logging.info("🖥️ Tray icon ready")
        except Exception as e:
            logging.warning(f"Tray icon error: {e}")
    else:
        logging.info("🖥️ Tray disabled. Running in standard console mode.")

    try:
        from core.ui.agent_status import reset_agent_status
        reset_agent_status()
        logging.info("🧹 Agent status reset to IDLE.")
    except Exception as e:
        logging.warning(f"Could not reset agent status: {e}")
    

    start_agent_panel()
    start_stt_popup()
    start_background_cache_builder()

    if not is_dev_mode:
        logging.info("Booting system...")
        time.sleep(1)

    try:
        memory = ContextMemory()
    except Exception as e:
        logging.error(f"Memory init failed: {e}")
        class FakeMemory:
            def get_relevant_context(self, text): return ""
            def add_message(self, role, text): pass
            preferences = {"likes": []}
            ephemeral = {}
        memory = FakeMemory()

    mode = "TEXT" if is_dev_mode else "VOICE"
    if mode == "VOICE":
        logging.info("🎙️ Listening... wake word: 'Jarvis'")
    logging.info("✅ Ready. (Groq + Gemini Embeddings)")

    if mode == "VOICE":
        stt.start_background_wake_word_listener()   

    with ThreadPoolExecutor(max_workers=5) as executor:
        
        def run_popup_task():
            global _is_popup_open

            if _is_popup_open:
                logging.info("⏳ Popup is already open. Ignoring duplicate hotkey press.")
                return
            
            try:
                _is_popup_open = True
                base_dir = os.path.dirname(os.path.abspath(__file__))

                popup_exe = os.path.join(base_dir, "Bin", "InputPopup.exe")
                creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
                
                result = subprocess.run(
                    [popup_exe],
                    capture_output=True,
                    text=True,
                    creationflags=creation_flags
                )
                
                cmd = ""
                for line in result.stdout.splitlines():
                    if "JARVIS_CMD:::" in line:
                        cmd = line.split("JARVIS_CMD:::")[1].strip()
                        break
                
                if cmd:
                    logging.info(f"⚡ Hotkey Command Received: {cmd}")
                    try:
                        hide_stt_popup()
                    except:
                        pass
                    
                    if _is_busy and hasattr(memory, 'add_live_feedback'):
                        logging.warning("🔄 Jarvis is currently busy. Injecting hotkey command as Live Feedback!")
                        memory.add_live_feedback(cmd)
                    else:
                        executor.submit(main_command_processor, cmd, executor, memory)
            except Exception as e:
                logging.error(f"Popup error: {e}")
            finally:
                _is_popup_open = False

        keyboard.add_hotkey('ctrl+shift+j', lambda: threading.Thread(target=run_popup_task, daemon=True).start())

        
        while _is_running:
            try:
                command = ""
                if mode == "TEXT":
                    try:
                        command = input("\n❯ ").strip()
                        if command:
                            logging.info(f"You said: {command}")
                    except EOFError:
                        break
                else:
                    command = stt.listen()
                    if not command:
                        continue

                if command and command.lower() in ["exit", "quit", "stop", "bye"]:
                    logging.info("Shutting down...")
                    _is_running = False
                    tts.stop_speaking()
                    break

                if command:
                    if _is_busy and hasattr(memory, 'add_live_feedback'):
                        logging.warning(f"🔄 Jarvis is busy. Injecting voice command '{command}' as Live Feedback!")
                        memory.add_live_feedback(command)
                        interrupt.clear_interrupt()
                    else:
                        try:
                            hide_stt_popup()
                        except Exception as e:
                            logging.debug(f"Hide popup error: {e}")
                        
                        executor.submit(main_command_processor, command, executor, memory)
                        interrupt.clear_interrupt()

            except KeyboardInterrupt:
                logging.info("Interrupted by user. Exiting.")
                _is_running = False
                break
            except Exception as e:
                logging.exception(f"Loop error: {e}")
                continue

    try:
        tts.cleanup_temp()
        pygame.quit()
    except:
        pass
    stop_agent_panel()
    stop_stt_popup()
    proc_manager.cleanup()  

if __name__ == "__main__":
    main()