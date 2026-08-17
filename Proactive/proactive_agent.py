import os
import time
import json
import re
import hashlib
import threading
import queue
from typing import Dict, Any
from groq import Groq, GroqError
from Proactive.SemanticSpam import check_semantic_spam
from core.logger.logger import logger
from core.brain.config import GROQ_API_KEY, AGENT_PROACTIVE
from core.voice.tts import speak
from core.brain.Processor.AgenticBrain import run_agentic_loop
from Proactive.event_queue import get_batched_events, _agent_task_queue
from Proactive.prompts import PROACTIVE_SCOUT_PROMPT
from Proactive.Email.EmailProactive import listen_for_emails, stop_email_listener
from Proactive.Whatsapp.WhatsappProactive import listen_for_whatsapp
from Proactive.Reminder.ReminderProactive import listen_for_reminders
from Proactive.Telegram.TelegramProactive import listen_for_telegram, stop_telegram_listener
from Proactive.SystemP.PCMonitorProactive import listen_for_pc_monitor, stop_pc_monitor
from core.ui.agent_status import update_agent_status, reset_agent_status

PROACTIVE_AGENT = AGENT_PROACTIVE
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
_stop_proactive = threading.Event()

_processed_events_cache = {}
CACHE_TTL = 300

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
    
    if event_hash in _processed_events_cache:
        if current_time - _processed_events_cache[event_hash] < CACHE_TTL:
            return True
        else:
            del _processed_events_cache[event_hash]
    return False

def mark_event_as_processed(source: str, text: str):
    event_hash = _get_event_hash(source, text)
    _processed_events_cache[event_hash] = time.time()

def stop_proactive_agent():
    _stop_proactive.set()
    stop_email_listener()
    stop_telegram_listener()
    stop_pc_monitor()

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

def evaluate_events_batch(batched_data: str, recent_history: str, current_mood: str) -> Dict[str, Any]:
    default_ignore = {"decision": "IGNORE", "emotion_tag": "[calm]", "announcement": "", "agent_command": ""}
    if not groq_client:
        return default_ignore
    backoff = 2
    for attempt in range(3):
        try:
            prompt = PROACTIVE_SCOUT_PROMPT.format(
                mood=current_mood,
                history=recent_history,
                batched_data=batched_data
            )
            completion = groq_client.chat.completions.create(
                model=PROACTIVE_AGENT,
                messages=[
                    {"role": "system", "content": "You are Jarvis's proactive intelligence. Return strict JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            raw_response = completion.choices[0].message.content.strip()
            cleaned_json = clean_json_string(raw_response)
            return json.loads(cleaned_json)
        except GroqError as ge:
            logger.warning(f"Groq API Error in Proactive Scout (Attempt {attempt+1}): {ge}")
            time.sleep(backoff)
            backoff *= 2
        except Exception as e:
            logger.error(f"Proactive evaluation error: {e}")
            return default_ignore
    return default_ignore

def safe_proactive_speak(text: str, memory_instance):
    def _speak_task():
        update_agent_status(step=1, total_steps=1, thought="Announcing...", action="SPEAKING", action_detail="", tokens=0)
        try:
            speak(text)
            time.sleep(1.0)
        finally:
            reset_agent_status()
            if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
                memory_instance.get_and_clear_feedback()
    threading.Thread(target=_speak_task, daemon=True).start()

def agentic_worker():
    while not _stop_proactive.is_set():
        try:
            task = _agent_task_queue.get(timeout=2)
            agent_command = task.get("agent_command")
            agent_context = task.get("agent_context")
            memory_instance = task.get("memory_instance")
            decision = task.get("decision")
            
            result = run_agentic_loop(agent_command, agent_context, memory_instance, silent=True)
            if result and result.get("response"):
                reply_text = result["response"]
                logger.info(f"Proactive Agent Confirmation: {reply_text}")
                safe_proactive_speak(reply_text, memory_instance)
                if memory_instance:
                    memory_instance.add_message(
                        "PROACTIVE_BACKGROUND",
                        reply_text,
                        metadata={
                            "is_background_event": False,
                            "decision": decision,
                            "waiting_for_confirmation": True
                        }
                    )
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Failed to execute background Agentic Brain: {e}")

def handle_proactive_decision(decision_data: Dict[str, Any], batched_data: str, memory_instance, is_jarvis_busy_callback):
    decision = decision_data.get("decision", "IGNORE").upper()
    announcement = decision_data.get("announcement", "").strip()
    agent_command = decision_data.get("agent_command", "").strip()
    
    if "IGNORE" in decision:
        return
        
    if is_jarvis_busy_callback:
        was_busy = False
        while is_jarvis_busy_callback() and not _stop_proactive.is_set():
            was_busy = True
            time.sleep(1)
        if was_busy:
            time.sleep(5)
            
    if decision in ["SUGGEST_ACTION", "ACT_AND_ANNOUNCE"] and agent_command:
        logger.info(f"Proactive Triggering Silent Agentic Brain: {agent_command}")
        _agent_task_queue.put({
            "agent_command": agent_command,
            "agent_context": f"[PROACTIVE EVENT TRIGGER]\n{batched_data}",
            "memory_instance": memory_instance,
            "decision": decision
        })
        return
        
    if decision == "ANNOUNCE" and announcement:
        logger.info(f"Proactive Announcement: {announcement}")
        safe_proactive_speak(announcement, memory_instance)
        if memory_instance:
            try:
                truncated_data = batched_data if len(batched_data) <= 2000 else batched_data[:2000] + "\n\n[...Message Truncated]"
                memory_instance.add_message(
                    "PROACTIVE_BACKGROUND",
                    announcement,
                    metadata={
                        "is_background_event": True,
                        "decision": decision,
                        "original_data": truncated_data
                    }
                )
            except Exception as mem_err:
                logger.warning(f"Failed to add proactive message to memory: {mem_err}")

def proactive_loop(memory_instance, is_jarvis_busy_callback):
    logger.info("Proactive Scout Agent initialized and listening...")
    while not _stop_proactive.is_set():
        try:
            events = get_batched_events(window_seconds=4)
            if events:
                valid_events = []
                for ev in events:
                    if not is_instant_spam(ev.data) and not check_semantic_spam(ev.data) and not is_event_already_processed(ev.source, ev.data):
                        valid_events.append(ev)
                if valid_events:
                    batched_data = "\n---\n".join([
                        f"Source: {ev.source} | Priority: {ev.priority} | Time: {ev.timestamp.strftime('%I:%M %p')}\nData: {ev.data}"
                        for ev in valid_events
                    ])
                    recent_history = "No recent history."
                    current_mood = "Neutral"
                    if memory_instance:
                        try:
                            recent_history = memory_instance.get_fast_history_context()
                            mood_history = memory_instance.user_mood.get("mood_history", [])
                            if mood_history:
                                current_mood = mood_history[-1].get("mood", "Neutral")
                        except Exception as mem_err:
                            logger.warning(f"Failed to fetch memory context: {mem_err}")
                            
                    decision_data = evaluate_events_batch(batched_data, recent_history, current_mood)
                    handle_proactive_decision(decision_data, batched_data, memory_instance, is_jarvis_busy_callback)
                    
                    if decision_data.get("decision", "IGNORE").upper() != "IGNORE":
                        for ev in valid_events:
                            mark_event_as_processed(ev.source, ev.data)
        except Exception as e:
            logger.error(f"Error in Proactive Loop: {e}")
        time.sleep(2)

def start_proactive_agent(memory_instance, is_jarvis_busy_callback=None):
    brain_thread = threading.Thread(target=proactive_loop, args=(memory_instance, is_jarvis_busy_callback), daemon=True)
    brain_thread.start()
    
    worker_thread = threading.Thread(target=agentic_worker, daemon=True)
    worker_thread.start()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    session_dir = os.path.join(base_dir, "Data", "SessionCookies")

    email_token = os.path.join(session_dir, "token.json")
    calendar_token = os.path.join(session_dir, "calendar_token.json")
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
            if os.path.exists(cred_path):
                t = threading.Thread(target=listener_func, daemon=True)
                t.start()
                logger.info(f"Started Proactive Listener: {name}")
            else:
                logger.info(f"Skipping {name} listener (not logged in)")
        except Exception as e:
            logger.error(f"Failed to start listener {name}: {e}")

    try:
        t = threading.Thread(target=listen_for_pc_monitor, daemon=True)
        t.start()
        logger.info("Started Proactive Listener: PC Monitor")
    except Exception as e:
        logger.error(f"Failed to start PC Monitor: {e}")

    return brain_thread