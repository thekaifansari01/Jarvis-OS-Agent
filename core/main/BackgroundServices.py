import os
import sys
import subprocess
import platform
import logging
from core.utils.ProcessManager import proc_manager
from core.voice.stt_status import exit_stt_popup

_panel_process = None
_stt_popup_process = None
_baileys_process = None

def start_agent_panel():
    global _panel_process
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        panel_script = os.path.join(base_dir, "core", "ui", "agent_panel.py")
        if os.path.exists(panel_script):
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            _panel_process = proc_manager.spawn(
                [sys.executable, panel_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
    except Exception as e:
        logging.error(f"Agent panel start failed: {e}")

def stop_agent_panel():
    global _panel_process
    if _panel_process:
        try:
            proc_manager.kill_process_tree(_panel_process.pid)
            _panel_process.wait(timeout=2)
        except Exception:
            pass
        _panel_process = None

def start_stt_popup():
    global _stt_popup_process
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        popup_exe = os.path.join(base_dir, "Bin", "SttPopup.exe")
        if os.path.exists(popup_exe):
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            _stt_popup_process = proc_manager.spawn(
                [popup_exe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
    except Exception as e:
        logging.error(f"STT popup start failed: {e}")

def stop_stt_popup():
    global _stt_popup_process
    try:
        exit_stt_popup()
    except Exception:
        pass
    if _stt_popup_process:
        try:
            proc_manager.kill_process_tree(_stt_popup_process.pid)
            _stt_popup_process.wait(timeout=2)
        except Exception:
            pass
        _stt_popup_process = None

def start_baileys_server():
    global _baileys_process
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        baileys_dir = os.path.join(base_dir, "tools", "Messanger", "whatsapp", "BaileysServer")
        script_path = os.path.join(baileys_dir, "baileys_service.js")
        session_creds_path = os.path.join(base_dir, "Data", "SessionCookies", "auth_info_baileys", "creds.json")
        
        if os.path.exists(script_path):
            creation_flags = 0
            stdout_target = None
            stderr_target = None
            
            if platform.system() == 'Windows':
                creation_flags = subprocess.CREATE_NEW_CONSOLE if not os.path.exists(session_creds_path) else subprocess.CREATE_NO_WINDOW
            
            _baileys_process = proc_manager.spawn(
                ["node", script_path],
                cwd=baileys_dir,
                stdout=stdout_target,
                stderr=stderr_target,
                creationflags=creation_flags
            )
    except Exception as e:
        logging.error(f"Baileys server start failed: {e}")

def stop_baileys_server():
    global _baileys_process
    if _baileys_process:
        try:
            proc_manager.kill_process_tree(_baileys_process.pid)
            _baileys_process.wait(timeout=2)
        except Exception:
            pass
        _baileys_process = None

def stop_all_services():
    stop_agent_panel()
    stop_stt_popup()
    stop_baileys_server()