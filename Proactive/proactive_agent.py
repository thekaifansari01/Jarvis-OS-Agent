# proactive_agent.py
import time
import threading
from groq import Groq, GroqError

from core.logger.logger import logger
from core.brain.config import GROQ_API_KEY
from core.voice.tts import speak
from Proactive.event_queue import get_proactive_event
from Proactive.prompts import PROACTIVE_SCOUT_PROMPT
from Proactive.Email.EmailProactive import listen_for_emails, stop_email_listener
from Proactive.Whatsapp.WhatsappProactive import listen_for_whatsapp
from Proactive.Reminder.ReminderProactive import listen_for_reminders
from core.brain.config import AGENT_PROACTIVE

PROACTIVE_AGENT = AGENT_PROACTIVE
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
_stop_proactive = threading.Event()

def stop_proactive_agent():
    _stop_proactive.set()
    stop_email_listener()

def evaluate_event(source: str, data: str, priority: str, recent_history: str, current_mood: str) -> str:
    if not groq_client:
        return "IGNORE"
    backoff = 2
    for attempt in range(3):
        try:
            prompt = PROACTIVE_SCOUT_PROMPT.format(
                source=source,
                data=data,
                priority=priority,
                history=recent_history,
                mood=current_mood
            )
            completion = groq_client.chat.completions.create(
                model=PROACTIVE_AGENT,
                messages=[
                    {"role": "system", "content": "You are Jarvis's proactive intelligence. Strictly follow the prompt's formatting and personality rules."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=150
            )
            return completion.choices[0].message.content.strip()
        except GroqError as ge:
            logger.warning(f"Groq API Error in Proactive Scout (Attempt {attempt+1}): {ge}")
            time.sleep(backoff)
            backoff *= 2
        except Exception as e:
            logger.error(f"❌ Proactive evaluation error: {e}")
            return "IGNORE"
    return "IGNORE"

def proactive_loop(memory_instance, is_jarvis_busy_callback):
    logger.info("🛡️ Proactive Scout Agent initialized and listening...")
    while not _stop_proactive.is_set():
        try:
            event = get_proactive_event()
            if event:
                source = event.source
                data = event.data
                priority = getattr(event, 'priority', 'normal')

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

                decision = evaluate_event(source, data, priority, recent_history, current_mood)

                if "IGNORE" not in decision.upper():
                    if is_jarvis_busy_callback:
                        was_busy = False
                        while is_jarvis_busy_callback() and not _stop_proactive.is_set():
                            was_busy = True
                            time.sleep(1)
                        if was_busy:
                            time.sleep(5)

                    logger.info(f"📢 Proactive Announcement ({source}): {decision}")
                    threading.Thread(target=speak, args=(decision,), daemon=True).start()

                    if memory_instance:
                        try:
                            truncated_data = data if len(data) <= 2000 else data[:2000] + "\n\n[...Message Truncated]"
                            memory_instance.add_message(
                                "PROACTIVE",
                                decision,
                                metadata={
                                    "source": source,
                                    "original_data": truncated_data
                                }
                            )
                            logger.info("🧠 Proactive event injected into Memory with raw data.")
                        except Exception as mem_err:
                            logger.warning(f"Failed to add proactive message to memory: {mem_err}")
        except Exception as e:
            logger.error(f"❌ Error in Proactive Loop: {e}")
        time.sleep(2)

def start_proactive_agent(memory_instance, is_jarvis_busy_callback=None):
    brain_thread = threading.Thread(target=proactive_loop, args=(memory_instance, is_jarvis_busy_callback), daemon=True)
    brain_thread.start()

    active_listeners = [
        listen_for_emails,
        listen_for_whatsapp,
        listen_for_reminders,
    ]

    for listener_func in active_listeners:
        try:
            listener_thread = threading.Thread(target=listener_func, daemon=True)
            listener_thread.start()
            logger.info(f"✅ Started Proactive Listener: {listener_func.__name__}")
        except Exception as e:
            logger.error(f"❌ Failed to start listener {listener_func.__name__}: {e}")

    return brain_thread