import os
import subprocess
import threading
import platform
import logging
import keyboard
from concurrent.futures import ThreadPoolExecutor
from core.brain.Memory.Memory import ContextMemory
from core.voice import tts
from core.voice.stt_status import hide_stt_popup
from core.main.CommandHandler import main_command_processor, is_jarvis_busy

_is_popup_open = False

def run_popup_task(executor: ThreadPoolExecutor, memory: ContextMemory):
    global _is_popup_open

    if _is_popup_open:
        return
    
    try:
        _is_popup_open = True
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        popup_exe = os.path.join(base_dir, "Bin", "InputPopup.exe")
        
        if not os.path.exists(popup_exe):
            return

        creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
        
        popup_proc = subprocess.Popen(
            [popup_exe],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creation_flags
        )

        auth_result = {"status": False, "done": False}

        def run_auth():
            try:
                from core.auth.FaceAuth import authenticate_face
                res = authenticate_face()
                auth_result["status"] = res
                auth_result["done"] = True
                
                if not res and popup_proc.poll() is None:
                    popup_proc.terminate()
                    try:
                        tts.speak("Access denied. Biometric failed.")
                    except Exception:
                        pass
            except Exception:
                auth_result["status"] = False
                auth_result["done"] = True
                if popup_proc.poll() is None:
                    try:
                        popup_proc.terminate()
                    except Exception:
                        pass

        auth_thread = threading.Thread(target=run_auth, daemon=True)
        auth_thread.start()

        stdout, _ = popup_proc.communicate()
        
        if auth_result["done"] and not auth_result["status"]:
            return

        if not auth_result["done"]:
            auth_thread.join()
            if not auth_result["status"]:
                try:
                    tts.speak("Access denied. Biometric failed.")
                except Exception:
                    pass
                return
        
        cmd = ""
        if stdout:
            for line in stdout.splitlines():
                if "JARVIS_CMD:::" in line:
                    cmd = line.split("JARVIS_CMD:::")[1].strip()
                    break
        
        if cmd:
            try:
                hide_stt_popup()
            except Exception:
                pass
            
            if is_jarvis_busy() and hasattr(memory, 'add_live_feedback'):
                try:
                    memory.add_live_feedback(cmd)
                except Exception:
                    pass
            else:
                executor.submit(main_command_processor, cmd, executor, memory)
    except Exception as e:
        logging.error(f"Popup logic failed: {e}")
    finally:
        _is_popup_open = False

def setup_hotkeys(executor: ThreadPoolExecutor, memory: ContextMemory):
    try:
        keyboard.add_hotkey('ctrl+shift+j', lambda: threading.Thread(target=run_popup_task, args=(executor, memory), daemon=True).start())
    except Exception as e:
        logging.error(f"Hotkey binding failed: {e}")