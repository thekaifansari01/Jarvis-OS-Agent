import time
import logging
from concurrent.futures import ThreadPoolExecutor
from core.brain.Processor.Processor import process_command
from core.brain.executor import execute_actions
from core.brain.Memory.Memory import ContextMemory
from core.voice import interrupt
from core.utils.shutdown import is_shutdown as is_shutting_down

_is_busy = False


def is_jarvis_busy() -> bool:
    global _is_busy
    return _is_busy


def main_command_processor(command: str, executor: ThreadPoolExecutor, memory: ContextMemory, source: str = "voice") -> None:
    global _is_busy

    if is_shutting_down():
        logging.debug("Command dropped: shutdown in progress (source=%s)", source)
        return

    _is_busy = True

    try:
        if command is None:
            logging.warning("Command dropped: None received (source=%s)", source)
            return

        raw = command.strip() if command else ""

        if not raw:
            logging.warning("Command dropped: empty after trim (source=%s)", source)
            return

        if is_shutting_down():
            logging.debug("Command dropped: shutdown mid-processing (source=%s)", source)
            return

        if interrupt.is_interrupted():
            interrupt.clear_interrupt()
            logging.debug("Command dropped: interrupt flag set (source=%s)", source)
            return

        line_count = raw.count("\n") + 1
        preview = raw[:150].replace("\n", " ⏎ ")
        logging.info(
            "[%s] Processing command (%d chars, %d lines): %s",
            source, len(raw), line_count, preview
        )

        if source == "telegram_bot":
            if not hasattr(memory, "ephemeral") or not isinstance(memory.ephemeral, dict):
                memory.ephemeral = {}
            memory.ephemeral["force_silent_agentic"] = True

        result = process_command(raw, memory_instance=memory)

        if is_shutting_down():
            return

        if not isinstance(result, dict):
            logging.error(
                "[%s] process_command returned non-dict (%r). Coercing to error result.",
                source, type(result)
            )
            result = {
                "response": "Internal error: invalid process_command result",
                "error": "invalid_result",
            }

        logging.info("[%s] process_command returned keys: %s", source, sorted(result.keys()))

        execute_actions(result, executor)

        if source == "telegram_bot" and hasattr(memory, "ephemeral"):
            memory.ephemeral.pop("force_silent_agentic", None)

        if "response" not in result:
            result["response"] = "Action executed."

        metadata = result.get("metadata", {})
        if not metadata:
            apps_opened = result.get("apps_to_open", [])
            apps_closed = result.get("apps_to_close", [])
            sys_events = []

            if result.get("system_action"):
                sys_events.append(f"System Action: {result['system_action']}")
            if result.get("urls_to_open"):
                sys_events.append(f"Opened URLs: {', '.join(result['urls_to_open'])}")
            if result.get("workspace_file_to_open"):
                sys_events.append(f"Opened Workspace File: {result['workspace_file_to_open']}")

            if apps_opened or apps_closed or sys_events:
                metadata = {
                    "apps_opened": apps_opened,
                    "apps_closed": apps_closed,
                    "system_events": sys_events,
                    "files_touched": [],
                }

        try:
            memory.add_message("USER", raw)
            memory.add_message(
                "JARVIS",
                result.get("response", ""),
                metadata=metadata if metadata else None,
            )
        except Exception as exc:
            logging.error("Memory update failed: %s", exc, exc_info=True)

        if result.get("response"):
            time.sleep(0.1)

    except Exception as exc:
        logging.error("[%s] Command processor crash: %s", source, exc, exc_info=True)

    finally:
        _is_busy = False
        if memory and hasattr(memory, "get_and_clear_feedback"):
            try:
                memory.get_and_clear_feedback()
            except Exception as exc:
                logging.debug("Feedback cleanup failed: %s", exc)