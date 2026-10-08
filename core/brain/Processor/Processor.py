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
from core.brain.config import ROUTER_API_KEY, ROUTER_MODEL, ROUTER_ENDPOINT, FAST_BRAIN_API_KEY, FAST_BRAIN_MODEL, FAST_BRAIN_ENDPOINT

load_dotenv()


class GenericSemanticRouter:
    def __init__(self):
        self.api_key = ROUTER_API_KEY
        self.base_url = ROUTER_ENDPOINT
        self.model = ROUTER_MODEL
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

        trimmed_history = history_context[-350:].strip() if history_context else "No recent history."

        system_prompt = (
            "You are an enterprise AI semantic router. Classify the CURRENT user command into strict JSON "
            "with a single key 'route' having value either 'FAST' or 'AGENTIC'.\n\n"
            "CRITICAL RULE: Evaluate ONLY the [USER COMMAND] for routing. Use [RECENT CONVERSATION HISTORY] purely for context. "
            "If the new command contains MULTIPLE intents, ALWAYS prioritize routing to 'AGENTIC'.\n\n"
            "### CRITICAL INTENT EXTRACTION\n"
            "Ignore wake words, names, and conversational fillers (e.g., 'Hi', 'Hello', 'Jarvis', 'Please', 'Bhai'). "
            "Focus strictly on the CORE ACTION of the command. If the core action requires complex execution "
            "(email, files, terminal), route to 'AGENTIC'. If the command is purely a greeting with no action, "
            "or a simple lookup, route to 'FAST'.\n\n"
            "### FAST BRAIN RULES (ROUTE TO 'FAST' ONLY IF STRICTLY THESE)\n"
            "- Casual conversation, greetings, jokes, time, date, or personal chit-chat.\n"
            "- Simple hardware controls: volume up/down/mute, brightness, screen lock, sleep, or screenshots.\n"
            "- Simple app/web launching or closing: 'Open Chrome', 'Close Notepad', 'Launch YouTube'.\n"
            "- Direct media playback: 'Play [song/video] on YouTube'.\n"
            "- Simple real-time web lookups: weather forecasts, live scores, quick definitions, or news.\n"
            "- Simple factual 'How-to' queries: 'How to boil an egg', 'How to tie a tie'.\n\n"
            "### AGENTIC BRAIN RULES (ROUTE TO 'AGENTIC' IF REQUIRED)\n"
            "- Technical/Complex 'How-to' queries: 'How does my database work', 'How to code this script'.\n"
            "- Mobile Device Control: 'turn on phone hotspot', 'read my mobile SMS'.\n"
            "- Email or WhatsApp messaging.\n"
            "- File system CRUD operations.\n"
            "- Coding & Terminal: writing/executing scripts, CMD commands, pip/npm, or git.\n"
            "- Long-term memory retrieval: searching notes, facts, or calendar.\n"
            "- Advanced research: scraping, arxiv search, or deep research.\n"
            "- Compound multi-step workflows.\n"
            "- Image/Screen analysis.\n"
            "- ANY command modifying or analyzing a local file/system state.\n\n"
            "### FEW-SHOT EXAMPLES\n"
            "User: 'Hello Jarvis' -> {\"route\": \"FAST\"}\n"
            "User: 'Hi Jarvis, volume badha do' -> {\"route\": \"FAST\"}\n"
            "User: 'Hello Jarvis, mere desktop par ek test.txt file banao' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'Jarvis, Kaif ko email bhej do ki main late aaunga' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'Email account kaise banate hai?' -> {\"route\": \"FAST\"}\n"
            "User: 'React app kaise banate hai?' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'Chrome kholo aur aaj ka weather search karo' -> {\"route\": \"FAST\"}\n"
            "User: 'Is YouTube link ka video summary batao' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'Is image mein kya likha hai?' -> {\"route\": \"AGENTIC\"}\n"
            "User: 'Weather check karo aur ek python script likho' -> {\"route\": \"AGENTIC\"}"
        )

        user_content = f"[RECENT CONVERSATION HISTORY]\n{trimmed_history}\n\n[USER COMMAND]\n\"{command}\""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
            "max_tokens": 15,
            "response_format": {"type": "json_object"}
        }

        try:
            start_ts = time.perf_counter()
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=self.timeout
            )
            latency_ms = (time.perf_counter() - start_ts) * 1000

            if response.status_code == 200:
                raw_json = response.json()["choices"][0]["message"]["content"]
                data = json.loads(raw_json)
                route = data.get("route", "FAST").strip().upper()
                logger.info(f"Semantic Router [{latency_ms:.1f}ms] | Decision -> {route}")
                return "AGENTIC" if route == "AGENTIC" else "FAST"
            else:
                logger.warning(f"Router API non-200 status ({response.status_code}): {response.text[:100]}")

        except Exception as e:
            logger.warning(f"Router API failed ({e}). Attempting Fast Brain (Tier 2) fallback...")
            try:
                if FAST_BRAIN_API_KEY:
                    fallback_session = requests.Session()
                    fallback_session.headers.update({
                        "Authorization": f"Bearer {FAST_BRAIN_API_KEY}",
                        "Content-Type": "application/json"
                    })
                    
                    fallback_payload = {
                        "model": FAST_BRAIN_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content}
                        ],
                        "temperature": 0.0,
                        "max_tokens": 15,
                        "response_format": {"type": "json_object"}
                    }
                    
                    start_ts_fb = time.perf_counter()
                    response_fb = fallback_session.post(
                        f"{FAST_BRAIN_ENDPOINT}/chat/completions",
                        json=fallback_payload,
                        timeout=self.timeout
                    )
                    latency_ms_fb = (time.perf_counter() - start_ts_fb) * 1000
                    
                    if response_fb.status_code == 200:
                        raw_json_fb = response_fb.json()["choices"][0]["message"]["content"]
                        data_fb = json.loads(raw_json_fb)
                        route_fb = data_fb.get("route", "FAST").strip().upper()
                        logger.info(f"Tier 2 Semantic Router (Fast Brain) [{latency_ms_fb:.1f}ms] | Decision -> {route_fb}")
                        return "AGENTIC" if route_fb == "AGENTIC" else "FAST"
                    else:
                        logger.warning(f"Tier 2 Router API non-200 status ({response_fb.status_code}): {response_fb.text[:100]}")
            except Exception as e2:
                logger.warning(f"Tier 2 Router API failed ({e2}). Switching to Local Regex Fallback (Tier 3).")

        return None


router_engine = GenericSemanticRouter()


def get_local_fallback_route(command: str) -> str:
    cmd_lower = command.lower().strip()

    absolute_fast_patterns = [
        r'\b(volume|awaaz|sound|brightness|screenshot|lock|sleep|mute)\b',
        r'\b(open|kholo|close|band|start|launch)\b',
        r'\b(play|chalao|song|gana|music|youtube)\b',
        r'\b(weather|mausam|time|date|score|news|joke)\b',
        r'\b(hi|hello|hey|kaise ho|what is up|good morning|good evening)\b',
        r'^\s*(what is|kya hai|kya hota hai|who is|kaun hai)\s+\w+\s*$' # strictly short general queries
    ]
    
    agentic_strict_patterns = [
        r'\b(write|run|execute|create|make|banao|likho|chalao).{0,30}(python|script|code|file|folder|dir|react|app|server)\b',
        r'\b(send|write|bhejo|read|check|karo).{0,30}(email|mail|gmail|whatsapp|msg|message|telegram)\b',
        r'\b(analyze|analyse|read|describe|explain|dekho|dikhao).{0,30}(image|photo|picture|screenshot|screen)\b',
        r'\b(search|find|check|yaad|recall|batao|kahan).{0,30}(memory|history|vault|notes|kal|aaj)\b',
        r'\b(terminal|cmd|powershell|pip install|npm install|git clone|subprocess)\b',
        r'\b(arxiv|vault|deep research|scrape|webpage)\b',
        r'\b(calendar|reminder|event|schedule)\b',
        r'\b(turn on|turn off|connect|read|send|check|control|chalu|band|on|off).{0,30}(mobile|phone|smartphone|sms|hotspot|flight mode|wifi)\b',
        r'\b(mobile|phone).{0,30}(control|connect|hotspot|sms)\b',
        r'\b(how to).{0,30}(code|build|fix|error|debug|install)\b',
        r'\b(kaise).{0,30}(code|banayein|fix|error|install)\b'
    ]

    # Priority 1: Check for explicit agentic keywords
    for pattern in agentic_strict_patterns:
        if re.search(pattern, cmd_lower):
            return "AGENTIC"

    # Priority 2: Check for explicit fast keywords
    for pattern in absolute_fast_patterns:
        if re.search(pattern, cmd_lower):
            return "FAST"

    # Priority 3: If multiple verbs/actions are detected, default to Agentic (Compound command)
    action_words = re.findall(r'\b(and|aur|then|phir|baad mein)\b', cmd_lower)
    if len(action_words) > 0:
        return "AGENTIC"

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
                logger.info("Proactive Confirmation detected -> Routing directly to AGENTIC")
                return "AGENTIC"
            else:
                memory_instance.ephemeral["waiting_for_confirmation"] = False

    history_context = ""
    if memory_instance and hasattr(memory_instance, "get_fast_history_context"):
        try:
            history_context = memory_instance.get_fast_history_context()
        except Exception:
            history_context = ""

    cloud_decision = router_engine.analyze_route(command, history_context)
    if cloud_decision:
        return cloud_decision

    logger.info("Using Local Rule-Based Fallback Router...")
    return get_local_fallback_route(command)


def fetch_hybrid_response(raw_command: str, memory_instance=None) -> Optional[Dict[str, any]]:
    try:
        decision = get_route_decision(raw_command, memory_instance)

        if decision == "AGENTIC":
            logger.info("Smart Router: AGENTIC (Deep Tasks, Memory, Comms & Visual Analysis)")
            context_blocks = []

            is_silent = False
            if memory_instance and hasattr(memory_instance, "ephemeral"):
                is_silent = memory_instance.ephemeral.get("force_silent_agentic", False)

            if memory_instance:
                try:
                    logger.info("Fetching Initial Profile, Mood & Workspace Context...")
                    personal_context = memory_instance.get_relevant_context(raw_command)
                    if personal_context:
                        context_blocks.append(personal_context)
                except Exception as e:
                    logger.error(f"Memory Fetch Error: {e}")

            final_context = "\n".join(context_blocks)

            return run_agentic_loop(raw_command, final_context, memory_instance, silent=is_silent)
        else:
            logger.info("Smart Router: FAST (Direct Apps / Stateless Chat / Hardware)")

            if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
                cleared_feedback = memory_instance.get_and_clear_feedback()
                if cleared_feedback:
                    logger.info(f"Flushed pending live feedback: {cleared_feedback}")

            ephemeral = memory_instance.ephemeral if memory_instance else None
            return fetch_from_groq(raw_command, memory_instance, ephemeral)

    except Exception as e:
        logger.error(f"Smart Router Error: {e}. Defaulting to Fast Brain.")

        if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
            memory_instance.get_and_clear_feedback()

        return fetch_from_groq(raw_command, memory_instance)


def process_command(raw_command: str, memory_instance=None) -> Dict[str, any]:
    resolved_command = resolve_pronouns(raw_command)
    result = fetch_hybrid_response(resolved_command, memory_instance)

    if not result:
        return make_result("Connection failed. Please check your internet connection.", priority="low")

    return result