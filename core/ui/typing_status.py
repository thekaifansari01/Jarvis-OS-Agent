import json
import os
import logging
import subprocess
import sys
from pathlib import Path

TYPING_STATUS_FILE = "Data/typing_status.json"
_popup_process = None

def launch_popup():
    """Popup UI ko background mein launch karta hai agar wo pehle se nahi chal raha."""
    global _popup_process
    
    if _popup_process is None or _popup_process.poll() is not None:
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        popup_path = project_root / "core" / "ui" / "Popup" / "Popup.py"
        
        if popup_path.exists():
            try:
                _popup_process = subprocess.Popen([sys.executable, str(popup_path)])
                logging.info("🖥️ Streaming Popup UI launched.")
            except Exception as e:
                logging.error(f"Failed to launch popup: {e}")
        else:
            logging.error(f"Popup UI script not found at {popup_path}")

def update_typing_status(status: str, text: str = ""):
    """
    JSON update karta hai jise Popup real-time mein padhega.
    status: 'typing' (for Fast Brain stream), 'completed' (for Agent/End of stream)
    """
    try:
        os.makedirs(os.path.dirname(TYPING_STATUS_FILE), exist_ok=True)
        with open(TYPING_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": status, "text": text}, f)
    except Exception as e:
        logging.error(f"Failed to update typing status: {e}")