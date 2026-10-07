import os
import time
import json
import re
import hashlib
import threading
import queue
from typing import Dict, Any
import openai
from Proactive.SemanticSpam import check_semantic_spam
from core.logger.logger import logger
from core.brain.config import (
    PROACTIVE_API_KEY,
    PROACTIVE_MODEL,
    PROACTIVE_ENDPOINT,
)
from core.voice.tts import speak
from core.brain.Processor.AgenticBrain import run_agentic_loop
from Proactive.event_queue import get_batched_events, _agent_task_queue
from Proactive.prompts import PROACTIVE_SCOUT_PROMPT
from Proactive.Email.EmailProactive import listen_for_emails, stop_email_listener
from Proactive.Whatsapp.WhatsappProactive import listen_for_whatsapp, stop_whatsapp_listener
from Proactive.Reminder.ReminderProactive import listen_for_reminders, stop_reminder_listener
from Proactive.Telegram.TelegramProactive import listen_for_telegram, stop_telegram_listener
from core.ui.agent_status import update_agent_status, reset_agent_status

PROACTIVE_AGENT = PROACTIVE_MODEL
proactive_client = openai.OpenAI(
    api_key=PROACTIVE_API_KEY,
    base_url=PROACTIVE_ENDPOINT,
) if PROACTIVE_API_KEY else None

_stop_proactive = threading.Event()

_processed_events_cache = {}
_processed_cache_lock = threading.Lock()
CACHE_TTL = 300
CACHE_MAX_SIZE = 1000

_speech_queue = queue.Queue()
_speech_worker_started = False
_speech_worker_lock = threading.Lock()
_memory_lock = threading.Lock()

SPAM_KEYWORDS = [
    "newsletter", "unsubscribe", "promotions",
    "50% off", "sale starts", "cashback", "advertisement"
]


def _get_event_hash(source: str, text: str) -> str:
    clean_text = re.sub(r'\s+', ' ', text.strip().lower())
    return hashlib.md5(f"{source}_{clean_text}".encode('utf-8')).hexdigest()


def is_event_already_processed(source: str, text: str) -> bool:
    current_time = time.time()
    event_hash = _get_event_hash(source, text)
    with _processed_cache_lock:
        if event_hash in _processed_events_cache:
            if current_time - _processed_events_cache[event_hash] < CACHE_TTL:
                return True
            del _processed_events_cache[event_hash]
    return False


def mark_event_as_processed(source: str, text: str):
    event_hash = _get_event_hash(source, text)
    with _processed_cache_lock:
        _processed_events_cache[event_hash] = time.time()
        if len(_processed_events_cache) > CACHE_MAX_SIZE:
            cutoff = time.time() - CACHE_TTL
            stale = [k for k, v in _processed_events_cache.items() if v < cutoff]
            for k in stale:
                del _processed_events_cache[k]


def stop_proactive_agent():
    _stop_proactive.set()
    stop_email_listener()
    stop_telegram_listener()
    stop_whatsapp_listener()
    stop_reminder_listener()


def is_instant_spam(text: str) -> bool:
    text_lower = text.lower()
    for kw in SPAM_KEYWORDS:
        if re.search(rf'\b{re.escape(kw)}\b', text_lower):
            return True
    return False


def clean_json_string(raw_text: str) -> str:
    json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    return re.sub(r'^```json\n|```$', '', raw_text, flags=re.MULTILINE).strip()


def evaluate_events_batch(batched_data: str, recent_history: str) -> Dict[str, Any]:
    default_ignore = {"decision": "IGNORE", "emotion_tag": "[calm]", "agent_command": ""}
    if not proactive_client:
        return default_ignore

    backoff = 2
    use_json_mode = True

    for attempt in range(3):
        try:
            prompt = PROACTIVE_SCOUT_PROMPT.format(
                history=recent_history,
                batched_data=batched_data
            )

            kwargs = {
                "model": PROACTIVE_AGENT,
                "messages": [
                    {"role": "system", "content": "You are Jarvis's proactive intelligence. Return strict JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 1500,
            }
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            completion = proactive_client.chat.completions.create(**kwargs)
            raw_response = completion.choices[0].message.content.strip()
            cleaned_json = clean_json_string(raw_response)
            return json.loads(cleaned_json)
        except Exception as e:
            logger.warning(f"Proactive API error (Attempt {attempt + 1}): {e}")
            err_str = str(e).lower()
            if use_json_mode and ("response_format" in err_str or "json" in err_str):
                use_json_mode = False
            time.sleep(backoff)
            backoff *= 2

    return default_ignore


def _speech_worker():
    while not _stop_proactive.is_set():
        try:
            task = _speech_queue.get(timeout=2)
        except queue.Empty:
            continue

        text = task.get("text", "")
        memory_instance = task.get("memory_instance")

        try:
            update_agent_status(
                step=1, total_steps=1, thought="Announcing...",
                action="SPEAKING", action_detail="", tokens=0
            )
            speak(text)
            time.sleep(1.0)
        except Exception as e:
            logger.error(f"Speech error: {e}")
        finally:
            try:
                reset_agent_status()
            except Exception:
                pass
            if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
                try:
                    memory_instance.get_and_clear_feedback()
                except Exception:
                    pass


def _ensure_speech_worker():
    global _speech_worker_started
    with _speech_worker_lock:
        if not _speech_worker_started:
            t = threading.Thread(target=_speech_worker, daemon=True)
            t.start()
            _speech_worker_started = True


def safe_proactive_speak(text: str, memory_instance):
    _ensure_speech_worker()
    _speech_queue.put({"text": text, "memory_instance": memory_instance})


def _memory_add_message(memory_instance, role, text, metadata):
    if not memory_instance:
        return
    try:
        with _memory_lock:
            memory_instance.add_message(role, text, metadata=metadata)
    except Exception as e:
        logger.warning(f"Memory add_message failed: {e}")


def _memory_get_history(memory_instance):
    if not memory_instance:
        return "No recent history."
    try:
        with _memory_lock:
            return memory_instance.get_fast_history_context()
    except Exception as e:
        logger.warning(f"Memory get history failed: {e}")
        return "No recent history."


def agentic_worker(is_jarvis_busy_callback=None):
    while not _stop_proactive.is_set():
        try:
            task = _agent_task_queue.get(timeout=2)
        except queue.Empty:
            continue

        try:
            agent_command = task.get("agent_command")
            agent_context = task.get("agent_context")
            memory_instance = task.get("memory_instance")
            decision = task.get("decision")

            if is_jarvis_busy_callback:
                while is_jarvis_busy_callback() and not _stop_proactive.is_set():
                    time.sleep(1)

            if _stop_proactive.is_set():
                break

            result = run_agentic_loop(agent_command, agent_context, memory_instance, silent=True)

            if result and result.get("response"):
                reply_text = result["response"]
                logger.info(f"Agentic Brain Background Execution: {reply_text}")

                if is_jarvis_busy_callback:
                    while is_jarvis_busy_callback() and not _stop_proactive.is_set():
                        time.sleep(1)

                safe_proactive_speak(reply_text, memory_instance)

                _memory_add_message(
                    memory_instance,
                    "PROACTIVE_BACKGROUND",
                    reply_text,
                    metadata={
                        "is_background_event": False,
                        "decision": decision,
                        "waiting_for_confirmation": True
                    }
                )
        except Exception as e:
            logger.error(f"Failed to execute background Agentic Brain: {e}")


def handle_proactive_decision(decision_data, batched_data, memory_instance, is_jarvis_busy_callback):
    decision = decision_data.get("decision", "IGNORE").upper()
    agent_command = decision_data.get("agent_command", "").strip()

    if "IGNORE" in decision:
        return

    if is_jarvis_busy_callback:
        while is_jarvis_busy_callback() and not _stop_proactive.is_set():
            time.sleep(1)

    if decision == "SUGGEST_ACTION" and agent_command:
        logger.info(f"Proactive Scout Triggering Agentic Brain: {agent_command}")
        _agent_task_queue.put({
            "agent_command": agent_command,
            "agent_context": f"[PROACTIVE EVENT TRIGGER]\n{batched_data}",
            "memory_instance": memory_instance,
            "decision": decision
        })


def proactive_loop(memory_instance, is_jarvis_busy_callback):
    logger.info("Proactive Scout Agent initialized and listening...")
    while not _stop_proactive.is_set():
        try:
            events = get_batched_events(window_seconds=4)
            if events:
                valid_events = []
                for ev in events:
                    try:
                        if is_instant_spam(ev.data):
                            continue
                        if check_semantic_spam(ev.data):
                            continue
                        if is_event_already_processed(ev.source, ev.data):
                            continue
                        valid_events.append(ev)
                    except Exception as ev_err:
                        logger.warning(f"Event filter error: {ev_err}")
                        continue

                if valid_events:
                    batched_data = "\n---\n".join([
                        f"Source: {ev.source} | Priority: {ev.priority} | Time: {ev.timestamp.strftime('%I:%M %p')}\nData: {ev.data}"
                        for ev in valid_events
                    ])

                    recent_history = _memory_get_history(memory_instance)
                    decision_data = evaluate_events_batch(batched_data, recent_history)
                    handle_proactive_decision(
                        decision_data, batched_data, memory_instance, is_jarvis_busy_callback
                    )

                    if decision_data.get("decision", "IGNORE").upper() != "IGNORE":
                        for ev in valid_events:
                            mark_event_as_processed(ev.source, ev.data)
        except Exception as e:
            logger.error(f"Error in Proactive Loop: {e}")

        for _ in range(2):
            if _stop_proactive.is_set():
                break
            time.sleep(1)


def _resolve_session_dir():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "Data", "SessionCookies")


def _first_existing(*paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def start_proactive_agent(memory_instance, is_jarvis_busy_callback=None):
    _stop_proactive.clear()
    _ensure_speech_worker()

    brain_thread = threading.Thread(
        target=proactive_loop,
        args=(memory_instance, is_jarvis_busy_callback),
        daemon=True
    )
    brain_thread.start()

    worker_thread = threading.Thread(
        target=agentic_worker,
        args=(is_jarvis_busy_callback,),
        daemon=True
    )
    worker_thread.start()

    session_dir = _resolve_session_dir()

    email_token = _first_existing(
        os.path.join(session_dir, "token.enc"),
        os.path.join(session_dir, "token.json"),
    )
    calendar_token = _first_existing(
        os.path.join(session_dir, "calendar_token.enc"),
        os.path.join(session_dir, "calendar_token.json"),
    )
    whatsapp_creds = os.path.join(session_dir, "auth_info_baileys", "creds.json")
    telegram_session = os.path.join(session_dir, "jarvis_telegram_session.session")

    listener_checks = [
        ("Email", listen_for_emails, email_token),
        ("WhatsApp", listen_for_whatsapp, whatsapp_creds),
        ("Telegram", listen_for_telegram, telegram_session),
        ("Calendar Reminder", listen_for_reminders, calendar_token),
    ]

    for name, listener_func, cred_path in listener_checks:
        try:
            if cred_path and os.path.exists(cred_path):
                t = threading.Thread(target=listener_func, daemon=True)
                t.start()
                logger.info(f"Started Proactive Listener: {name}")
            else:
                logger.info(f"Skipping {name} listener (not logged in)")
        except Exception as e:
            logger.error(f"Failed to start listener {name}: {e}")

    return brain_thread