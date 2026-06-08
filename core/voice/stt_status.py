import json
import os
import logging

STATUS_FILE = "Data/stt_status.json"

def update_stt_status(status: str, text: str = ""):
    """Updates the STT JSON file to trigger the UI."""
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": status, "text": text}, f)
    except Exception as e:
        logging.error(f"Failed to update STT status: {e}")

def hide_stt_popup():
    """Forces the popup to hide by setting status to idle."""
    update_stt_status("idle", "")

def exit_stt_popup():
    """Tells the PyQt application to quit safely."""
    update_stt_status("exit", "")