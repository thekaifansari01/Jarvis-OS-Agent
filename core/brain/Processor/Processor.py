import os
import re
import json
import time
from typing import Dict, Optional
import requests
from dotenv import load_dotenv

from core.logger.logger import logger
from core.utils.utils import resolve_pronouns
from core.brain.Processor.FastBrain import fetch_from_groq, make_result
from core.brain.Processor.AgenticBrain import run_agentic_loop

load_dotenv()
REGOLO_API_KEY = os.getenv("REGOLO_API_KEY")


class RegoloSemanticRouter:
    def __init__(self):
        self.api_key = REGOLO_API_KEY
        self.base_url = "https://api.regolo.ai/v1/chat/completions"
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            })
        self.timeout = 2.0

    def analyze_route(self, command: str, history_context: str = "") -> Optional[str]:
        if not self.api_key:
            return None
        
        system_prompt = (
            "You are an enterprise AI semantic router. Your task is to classify user commands into strict JSON "
            "with a single key 'route' having value either 'FAST' or 'AGENTIC'.\n\n"
            "### ROUTING RULES (ORDER OF PRIORITY)\n"
            "1. ROUTE TO 'AGENTIC' IF THE COMMAND REQUIRES:\n"
            "   - Sending emails or WhatsApp messages/fetching chat history.\n"
            "   - Creating, reading, editing, or deleting local files (txt, md, code) or folders.\n"
            "   - Writing or running Python code, terminal/CMD commands, or package installations (pip/npm).\n"
            "   - Recalling past memories, instructions, personal vault notes, or calendar events.\n"
            "   - Scraping webpages, summarizing YouTube links, academic paper search (arxiv), or deep research reports.\n"
            "   - Creating/editing AI images or reading/writing system clipboard.\n"
            "   - ANY compound command combining multiple steps (e.g., 'Open Chrome and send an email').\n\n"
            "2. ROUTE TO 'FAST' IF THE COMMAND IS:\n"
            "   - General conversation, greetings, jokes, or casual chat.\n"
            "   - Simple real-time factual checks (weather, live sports scores, quick news).\n"
            "   - DIRECT SYSTEM CONTROLS: Opening/closing standard desktop apps or websites (Chrome, Notepad, etc.).\n"
            "   - Hardware controls: Volume up/down/mute, brightness, lock PC, sleep PC, or taking a screenshot.\n"
            "   - DIRECT MEDIA PLAYBACK: 'Play [song/video] on YouTube' without requiring summary/analysis.\n\n"
            "### FEW-SHOT EXAMPLES (ENGLISH & HINGLISH)\n"
            "User: 'Volume badha do aur Youtube par Arijit Singh ka gana chalao' -> {\"route\": \"FAST\"}\n"
            "User: 'Chrome kholo aur weather check karo' -> {\"route\": \"FAST\"}\n"
            "User: 'Is YouTube link ka video summary batao' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'Kaif ko mail bhejo ki meeting 5 baje hai' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'Desktop par ek naya file bano test.txt nam se' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'Kal maine tumse kya kaha tha coffee ke bare me?' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'System lock kar do' -> {\"route\": \"FAST\"}"
        )

        user_content = f"[RECENT CONVERSATION HISTORY]\n{history_context if history_context else 'No recent history.'}\n\n[USER COMMAND]\n\"{command}\""

        payload = {
            "model": "brick-complexity-pro",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
            "max_tokens": 20,
            "response_format": {"type": "json_object"}
        }

        try:
            start_ts = time.perf_counter()
            response = self.session.post(self.base_url, json=payload, timeout=self.timeout)
            latency_ms = (time.perf_counter() - start_ts) * 1000

            if response.status_code == 200:
                raw_json = response.json()["choices"][0]["message"]["content"]
                data = json.loads(raw_json)
                route = data.get("route", "FAST").strip().upper()
                logger.info(f"⚡ Regolo Semantic Router [{latency_ms:.1f}ms] | Decision -> {route}")
                return "AGENTIC" if route == "AGENTIC" else "FAST"
        except Exception as e:
            logger.warning(f"⚠️ Regolo Router API failed ({e}). Switching to local fallback router.")
            
        return None


router_engine = RegoloSemanticRouter()


def get_local_fallback_route(command: str) -> str:
    if len(command.split()) > 25:
        return "AGENTIC"
    cmd_lower = command.lower()
    
    agentic_overrides = [
        "email", "mail", "whatsapp", "file", "terminal", "code", "python", "read", "padho",
        "write", "likho", "summary", "search", "dhoondho", "memory", "yaad", "resume",
        "bano", "bhejo"
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

    return "FAST"


def get_route_decision(command: str, memory_instance=None) -> str:
    if memory_instance and hasattr(memory_instance, "ephemeral"):
        if memory_instance.ephemeral.get("waiting_for_confirmation"):
            cmd_lower = command.lower().strip()
            confirm_keywords = [
                "haa", "ha", "yes", "yup", "han", "ha kar de", "ha krde", 
                "theek hai", "ok", "okay", "do it", "kar do", "kardo", "bilkul"
            ]
            if any(kw in cmd_lower for kw in confirm_keywords):
                memory_instance.ephemeral["waiting_for_confirmation"] = False
                logger.info("⚡ Proactive Confirmation detected -> Routing directly to AGENTIC")
                return "AGENTIC"

    history_context = ""
    if memory_instance and hasattr(memory_instance, "get_fast_history_context"):
        try:
            history_context = memory_instance.get_fast_history_context()
        except Exception:
            history_context = ""

    cloud_decision = router_engine.analyze_route(command, history_context)
    if cloud_decision:
        return cloud_decision

    logger.info("🔄 Using Local Rule-Based Fallback Router...")
    return get_local_fallback_route(command)


def fetch_hybrid_response(raw_command: str, memory_instance=None) -> Optional[Dict[str, any]]:
    try:
        decision = get_route_decision(raw_command, memory_instance)
        
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