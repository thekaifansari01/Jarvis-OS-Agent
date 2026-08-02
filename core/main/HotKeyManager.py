import os
import subprocess
import threading
import platform
import logging
import keyboard
from concurrent.futures import ThreadPoolExecutor
from core.brain.Memory.Memory import ContextMemory
from core.voice.stt_status import hide_stt_popup
from core.main.CommandHandler import main_command_processor, is_jarvis_busy

_is_popup_open = False


def run_popup_task(executor: ThreadPoolExecutor, memory: ContextMemory):
    """
    Triggered by hotkey. Opens InputPopup.exe, reads the typed command,
    and submits it to the main processor.
    """
    global _is_popup_open

    if _is_popup_open:
        return

    try:
        _is_popup_open = True

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        popup_exe = os.path.join(base_dir, "Bin", "InputPopup.exe")

        if not os.path.exists(popup_exe):
            logging.warning("InputPopup.exe not found. Hotkey disabled.")
            return

        creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0

        popup_proc = subprocess.Popen(
            [popup_exe],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creation_flags
        )

        stdout, _ = popup_proc.communicate()

        cmd = ""
        if stdout:
            for line in stdout.splitlines():
                if "JARVIS_CMD:::" in line:
                    cmd = line.split("JARVIS_CMD:::")[1].strip()
                    break

        if cmd:
            try:
                hide_stt_popup()
            except Exception as exc:
                logging.debug("Could not hide the STT popup before processing typed input: %s", exc, exc_info=True)

            if is_jarvis_busy() and hasattr(memory, 'add_live_feedback'):
                try:
                    memory.add_live_feedback(cmd)
                except Exception as exc:
                    logging.error("Could not save typed input as live feedback: %s", exc, exc_info=True)
            else:
                executor.submit(main_command_processor, cmd, executor, memory)

    except Exception as e:
        logging.error(f"Popup logic failed: {e}")
    finally:
        _is_popup_open = False


def setup_hotkeys(executor: ThreadPoolExecutor, memory: ContextMemory):
    """
    Binds Ctrl+Shift+J to launch the text input popup.
    """
    try:
        keyboard.add_hotkey(
            'ctrl+shift+j',
            lambda: threading.Thread(target=run_popup_task, args=(executor, memory), daemon=True).start()
        )
        logging.info("✅ Hotkey Ctrl+Shift+J registered for text input.")
    except Exception as e:
        logging.error(f"Hotkey binding failed: {e}")
