from typing import Dict, Optional
from groq import Groq

from core.logger.logger import logger       
from core.utils.utils import resolve_pronouns
from core.brain.config import GROQ_ROUTER_MODEL, GROQ_API_KEY

from core.brain.Processor.Prompts import ROUTER_PROMPT
from core.brain.Processor.FastBrain import fetch_from_groq, make_result
from core.brain.Processor.AgenticBrain import run_agentic_loop

ROUTER_MODEL = GROQ_ROUTER_MODEL
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def fetch_hybrid_response(raw_command: str, memory_instance=None) -> Optional[Dict[str, any]]:
    if not groq_client: return None
    try:
        recent_context = "No recent conversation."
        if memory_instance:
            try:
                recent_context = memory_instance.get_fast_history_context()
            except Exception as e:
                logger.warning(f"Could not fetch recent context for router: {e}")

        router_system_prompt = ROUTER_PROMPT.format(recent_context=recent_context)

        completion = groq_client.chat.completions.create(
            model=ROUTER_MODEL,
            messages=[
                {"role": "system", "content": router_system_prompt},
                {"role": "user", "content": raw_command}
            ],
            temperature=0.0,
            max_tokens=10
        )
        decision = completion.choices[0].message.content.strip().upper()
        
        if "FAST" in decision:
            decision = "FAST"
        else:
            decision = "AGENTIC"
        
        if decision == "AGENTIC":
            logger.info("🚦 Smart Router: AGENTIC (Deep Tasks, Memory & Comms)")
            context_blocks = []
            
            if memory_instance: 
                try:
                    logger.info("🗂️ Fetching 15-Day Master Memory Context...")
                    personal_context = memory_instance.get_relevant_context(raw_command)
                    if personal_context:
                        context_blocks.append(personal_context)
                except Exception as e:
                    logger.error(f"Memory Fetch Error: {e}")

            final_context = "\n".join(context_blocks)
            
            return run_agentic_loop(raw_command, final_context, memory_instance)
        else:
            logger.info("🚦 Smart Router: FAST (Direct Apps / Stateless Chat / File Open)")
            
            if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
                cleared_feedback = memory_instance.get_and_clear_feedback()
                if cleared_feedback:
                    logger.info(f"🗑️ Flushed pending live feedback (Not needed for Fast Route): {cleared_feedback}")

            ephemeral = memory_instance.ephemeral if memory_instance else None
            return fetch_from_groq(raw_command, memory_instance, ephemeral)
            
    except Exception as e:
        logger.error(f"⚠️ Smart Router Error: {e}. Defaulting to Fast Brain.")
        
        if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
            memory_instance.get_and_clear_feedback()
            
        return fetch_from_groq(raw_command, memory_instance)


def process_command(raw_command: str, memory_instance=None) -> Dict[str, any]:
    resolved_command = resolve_pronouns(raw_command)
    result = fetch_hybrid_response(resolved_command, memory_instance)
    
    if not result:
        return make_result("Connection failed bhai, internet check karlo.", priority="low")

    return result