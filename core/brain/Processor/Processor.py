import re
from typing import Dict, Optional

from core.logger.logger import logger       
from core.utils.utils import resolve_pronouns
from core.brain.Processor.FastBrain import fetch_from_groq, make_result
from core.brain.Processor.AgenticBrain import run_agentic_loop

def get_route_decision(command: str) -> str:
    cmd_lower = command.lower()
    
    agentic_overrides = [
        "email", "whatsapp", "file", "terminal", "code", "python", "read", "padho", 
        "write", "likho", "summary", "search", "dhoondho", "memory", "yaad", "resume"
    ]
    
    fast_triggers = [
        "volume", "awaaz", "brightness", "screenshot", "lock", "sleep", "mute",
        "open", "kholo", "close", "band", "start", "launch",
        "youtube", "play", "song", "chalao", "music",
        "time", "date", "weather", "mausam", "hi", "hello", "kaise ho"
    ]

    for word in agentic_overrides:
        if re.search(rf'\b{re.escape(word)}\b', cmd_lower):
            return "AGENTIC"

    for word in fast_triggers:
        if re.search(rf'\b{re.escape(word)}\b', cmd_lower):
            return "FAST"

    return "AGENTIC"

def fetch_hybrid_response(raw_command: str, memory_instance=None) -> Optional[Dict[str, any]]:
    try:
        decision = get_route_decision(raw_command)
        
        if decision == "AGENTIC":
            logger.info("🚦 Smart Router: AGENTIC (Deep Tasks, Memory & Comms)")
            context_blocks = []
            
            if memory_instance: 
                try:
                    logger.info("🗂️ Fetching Initial Profile, Mood & Workspace Context...")
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
                    logger.info(f"🗑️ Flushed pending live feedback: {cleared_feedback}")

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