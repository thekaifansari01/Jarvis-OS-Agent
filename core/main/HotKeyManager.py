import os
import sys
import time
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
_is_agent_asking = False
_popup_state_lock = threading.Lock()
_active_popup_proc = None

_MARKER_B64 = "JARVIS_CMD_B64:::"
_MARKER_LEGACY = "JARVIS_CMD:::"
_POPUP_TIMEOUT_SECONDS = 1800


def is_popup_active() -> bool:
    with _popup_state_lock:
        return bool(_is_popup_open or _is_agent_asking)


def is_agent_asking_user() -> bool:
    with _popup_state_lock:
        return bool(_is_agent_asking)


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


def _spawn_and_capture_popup(question: str = "", placeholder: str = "", timeout_sec: int = _POPUP_TIMEOUT_SECONDS) -> str:
    global _active_popup_proc

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    popup_script = os.path.join(base_dir, "core", "ui", "InputPopup", "InputPopup.py")

    if not os.path.exists(popup_script):
        logging.warning("InputPopup.py not found at %s", popup_script)
        return ""

    try:
        hide_stt_popup()
    except Exception:
        pass

    creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONUNBUFFERED"] = "1"

    if question:
        child_env["JARVIS_ASK_QUESTION"] = question
    else:
        child_env.pop("JARVIS_ASK_QUESTION", None)

    if placeholder:
        child_env["JARVIS_ASK_PLACEHOLDER"] = placeholder
    else:
        child_env.pop("JARVIS_ASK_PLACEHOLDER", None)

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
    _active_popup_proc = popup_proc

    try:
        stdout, stderr = popup_proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        logging.error("InputPopup timed out after %s seconds. Killing popup.", timeout_sec)
        try:
            popup_proc.kill()
        except Exception:
            pass
        try:
            popup_proc.communicate(timeout=5)
        except Exception:
            pass
        return ""
    finally:
        _active_popup_proc = None

    if popup_proc.returncode not in (None, 0):
        logging.error("InputPopup exited with non-zero code: %s", popup_proc.returncode)

    if stderr:
        cleaned_stderr = stderr.strip()
        if cleaned_stderr:
            logging.warning("InputPopup stderr: %s", cleaned_stderr[:2000])

    return _decode_command_from_stdout(stdout)


def ask_user_via_popup(question: str, placeholder: str = "", timeout_sec: int = _POPUP_TIMEOUT_SECONDS) -> str:
    global _is_popup_open, _is_agent_asking, _active_popup_proc

    with _popup_state_lock:
        if _is_popup_open and _active_popup_proc is not None:
            try:
                _active_popup_proc.kill()
            except Exception:
                pass
        _is_popup_open = True
        _is_agent_asking = True

    try:
        time.sleep(0.05)
        cmd = _spawn_and_capture_popup(
            question=question,
            placeholder=placeholder,
            timeout_sec=timeout_sec,
        )
        logging.info("Agent ask_user InputPopup returned length: %d chars", len(cmd))
        return cmd
    except Exception as exc:
        logging.error("ask_user_via_popup failed: %s", exc, exc_info=True)
        return ""
    finally:
        with _popup_state_lock:
            _is_agent_asking = False
            _is_popup_open = False


def run_popup_task(executor: ThreadPoolExecutor, memory: ContextMemory):
    global _is_popup_open

    with _popup_state_lock:
        if _is_popup_open or _is_agent_asking:
            return
        _is_popup_open = True

    try:
        cmd = _spawn_and_capture_popup(question="", placeholder="")

        logging.info("InputPopup returned command length: %d chars", len(cmd))

        if not cmd:
            logging.warning("No command captured from popup.")
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
        with _popup_state_lock:
            if not _is_agent_asking:
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