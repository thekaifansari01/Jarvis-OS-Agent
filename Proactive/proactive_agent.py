import time
import threading
from groq import Groq

from core.logger.logger import logger
from core.brain.config import GROQ_API_KEY
from core.voice.tts import speak
from Proactive.event_queue import get_proactive_event
from Proactive.prompts import PROACTIVE_SCOUT_PROMPT
from Proactive.Email.EmailProactive import listen_for_emails
from Proactive.Whatsapp.WhatsappProactive import listen_for_whatsapp

SCOUT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct" 
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def evaluate_event(source: str, data: str, priority: str) -> str:
    if not groq_client: return "IGNORE"
    try:
        prompt = PROACTIVE_SCOUT_PROMPT.format(source=source, data=data, priority=priority)
        completion = groq_client.chat.completions.create(
            model=SCOUT_MODEL,
            messages=[
                {"role": "system", "content": "You are Jarvis's proactive intelligence. Strictly follow the prompt's formatting and personality rules."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=60
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ Proactive evaluation error: {e}")
        return "IGNORE"

def proactive_loop(memory_instance):
    logger.info("🛡️ Proactive Scout Agent initialized and listening...")
    while True:
        try:
            event = get_proactive_event()
            if event:
                source = event.source
                data = event.data
                priority = getattr(event, 'priority', 'normal') 
                
                decision = evaluate_event(source, data, priority)

                if decision.upper() != "IGNORE" and "IGNORE" not in decision.upper():
                    logger.info(f"📢 Proactive Announcement ({source}): {decision}")
                    threading.Thread(target=speak, args=(decision,), daemon=True).start()

                    if memory_instance:
                        try:
                            memory_instance.add_message(
                                "PROACTIVE", 
                                decision, 
                                metadata={"ephemeral_only": True, "source": source}
                            )
                            logger.info("🧠 Proactive event injected into 15-days Memory (JSON only).")
                        except Exception as mem_err:
                            logger.warning(f"Failed to add proactive message to memory: {mem_err}")
        except Exception as e:
            logger.error(f"❌ Error in Proactive Loop: {e}")
        time.sleep(2)

def start_proactive_agent(memory_instance):
    """
    main.py isko directly call karega bina kisi change ke.
    Ye function khud saare background listeners manage karega.
    """
    brain_thread = threading.Thread(target=proactive_loop, args=(memory_instance,), daemon=True)
    brain_thread.start()
    
    active_listeners = [
        listen_for_emails,
        listen_for_whatsapp,
    ]
    
    for listener_func in active_listeners:
        try:
            listener_thread = threading.Thread(target=listener_func, daemon=True)
            listener_thread.start()
            logger.info(f"✅ Started Proactive Listener: {listener_func.__name__}")
        except Exception as e:
            logger.error(f"❌ Failed to start listener {listener_func.__name__}: {e}")
            
    return brain_thread