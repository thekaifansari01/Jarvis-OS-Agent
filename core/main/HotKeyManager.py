import os
import sys
import base64
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

_MARKER_B64 = "JARVIS_CMD_B64:::"
_MARKER_LEGACY = "JARVIS_CMD:::"
_POPUP_TIMEOUT_SECONDS = 1800


def _decode_command_from_stdout(stdout):
    if not stdout:
        return ""
    for line in stdout.splitlines():
        if _MARKER_B64 in line:
            encoded = line.split(_MARKER_B64, 1)[1].strip()
            if not encoded:
                return ""
            try:
                return base64.b64decode(encoded).decode("utf-8", errors="replace")
            except Exception as exc:
                logging.error("Failed to decode base64 command from popup: %s", exc)
                return ""
        if _MARKER_LEGACY in line:
            legacy = line.split(_MARKER_LEGACY, 1)[1].strip()
            return legacy if legacy else ""
    return ""


def run_popup_task(executor: ThreadPoolExecutor, memory: ContextMemory):
    global _is_popup_open

    if _is_popup_open:
        return

    try:
        _is_popup_open = True

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        popup_script = os.path.join(base_dir, "core", "ui", "InputPopup", "InputPopup.py")

        if not os.path.exists(popup_script):
            logging.warning("InputPopup.py not found. Hotkey disabled.")
            return

        creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONUNBUFFERED"] = "1"

        popup_proc = subprocess.Popen(
            [sys.executable, popup_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
            creationflags=creation_flags,
        )

        try:
            stdout, stderr = popup_proc.communicate(timeout=_POPUP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            logging.error("InputPopup timed out after %s seconds. Killing popup.", _POPUP_TIMEOUT_SECONDS)
            try:
                popup_proc.kill()
            except Exception:
                pass
            try:
                popup_proc.communicate(timeout=5)
            except Exception:
                pass
            return

        if popup_proc.returncode not in (None, 0):
            logging.error("InputPopup exited with non-zero code: %s", popup_proc.returncode)

        if stderr:
            cleaned_stderr = stderr.strip()
            if cleaned_stderr:
                logging.warning("InputPopup stderr: %s", cleaned_stderr[:2000])

        cmd = _decode_command_from_stdout(stdout)

        logging.info("InputPopup returned command length: %d chars", len(cmd))

        if not cmd:
            logging.warning("No command captured from popup. raw stdout was: %r", (stdout or "")[:300])
            return

        try:
            hide_stt_popup()
        except Exception as exc:
            logging.debug("Could not hide STT popup: %s", exc, exc_info=True)

        if is_jarvis_busy() and hasattr(memory, "add_live_feedback"):
            try:
                memory.add_live_feedback(cmd)
                logging.info("Command injected as live feedback (Jarvis busy).")
            except Exception as exc:
                logging.error("Could not save typed input as live feedback: %s", exc, exc_info=True)
        else:
            logging.info("Submitting command to processor: %s", cmd[:100].replace("\n", " ⏎ "))
            executor.submit(main_command_processor, cmd, executor, memory)

    except Exception as exc:
        logging.error("Popup logic failed: %s", exc, exc_info=True)
    finally:
        _is_popup_open = False


def setup_hotkeys(executor: ThreadPoolExecutor, memory: ContextMemory):
    try:
        keyboard.add_hotkey(
            "ctrl+shift+j",
            lambda: threading.Thread(
                target=run_popup_task,
                args=(executor, memory),
                daemon=True,
            ).start(),
        )
        logging.info("✅ Hotkey Ctrl+Shift+J registered for text input.")
    except Exception as exc:
        logging.error("Hotkey binding failed: %s", exc)