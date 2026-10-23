import os
import re
import json
import time
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

from core.logger.logger import logger
from core.utils.utils import resolve_pronouns
from core.brain.Processor.FastBrain import fetch_from_groq, make_result, clean_json_string
from core.brain.Processor.AgenticBrain import run_agentic_loop
from core.brain.prompts import (
    VALID_PROMPT_DOMAINS,
    infer_domains_from_command,
    normalize_domains,
    select_behavioral_domain,
)
from core.brain.config import (
    ROUTER_API_KEY,
    ROUTER_MODEL,
    ROUTER_ENDPOINT,
    FAST_BRAIN_API_KEY,
    FAST_BRAIN_MODEL,
    FAST_BRAIN_ENDPOINT,
)

load_dotenv()

VALID_DOMAINS = VALID_PROMPT_DOMAINS


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
        self.timeout = 5.0

    @staticmethod
    def _safe_parse_json(raw_text: str) -> Optional[dict]:
        if not raw_text:
            return None
        text = clean_json_string(raw_text)
        try:
            return json.loads(text)
        except Exception:
            pass
        try:
            from json_repair import repair_json
            repaired = repair_json(text, return_objects=False)
            if isinstance(repaired, str):
                return json.loads(repaired)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass
        try:
            depth = 0
            in_str = False
            esc = False
            for i, ch in enumerate(text):
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return json.loads(text[: i + 1])
            if depth > 0:
                text = text + ("}" * depth)
            return json.loads(text)
        except Exception:
            return None

    @staticmethod
    def _parse_router_payload(data: dict, command: str) -> Dict[str, Any]:
        route = "AGENTIC" if str(data.get("route", "FAST")).strip().upper() == "AGENTIC" else "FAST"
        eng_q = str(data.get("english_query") or command).strip()

        raw_domains: List[str] = []
        if isinstance(data.get("domains"), list):
            raw_domains.extend(str(x) for x in data["domains"] if x)
        if data.get("domain"):
            raw_domains.append(str(data["domain"]))

        active_domains = normalize_domains(raw_domains, command)
        behavioral_domain = select_behavioral_domain(active_domains)
        primary_domain = active_domains[0] if active_domains else "general_none"

        return {
            "route": route,
            "english_query": eng_q,
            "domain": behavioral_domain,
            "primary_domain": primary_domain,
            "domains": active_domains,
        }

    def analyze_route_full(self, command: str, history_context: str = "") -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None

        trimmed_history = history_context[-800:].strip() if history_context else "No recent history."

        system_prompt = (
            "You are an enterprise AI semantic router. Classify the CURRENT user command into strict JSON "
            "with three keys:\n"
            "1. 'route': Either 'FAST' or 'AGENTIC'.\n"
            "2. 'english_query': A concise 4-10 word pure English translation of the user's core intent (strip Hinglish/fillers).\n"
            "3. 'domains': An array of 1 or 2 matching domain modules from: "
            "['coding', 'ui_design', 'gui_automation', 'communication', 'scheduling', 'lifestyle', 'research_memory', 'system_mobile', 'creator_identity', 'general_none'].\n"
            "   - 'coding': Writing/debugging code, scripts, backend, APIs, Python, Rust, PHP, JS, C++, SQL.\n"
            "   - 'ui_design': Web pages, dashboards, HTML/CSS/Tailwind/React, frontend layouts.\n"
            "   - 'gui_automation': Visually clicking buttons on screen, typing on UI, observing screen elements.\n"
            "   - 'communication': Drafting/sending/reading emails, WhatsApp, or Telegram messages.\n"
            "   - 'scheduling': Study plans, timetables, routines, productivity schedules, or Google Calendar events.\n"
            "   - 'lifestyle': Workout, diet, health, or daily habit advice.\n"
            "   - 'research_memory': Recalling personal facts/memories, searching local vault notes, ArXiv papers, YouTube transcripts, or deep research.\n"
            "   - 'system_mobile': Terminal/CMD commands, pip/npm/git, Android phone/Termux control, PC-mobile file transfer, clipboard, or AI image generation.\n"
            "   - 'creator_identity': Questions about who created/built Jarvis, Kaif Ansari, or Mindly.\n"
            "   - 'general_none': Casual chat, greetings, weather, live scores, volume/brightness, or simple app launching.\n\n"
            "CRITICAL RULE: Evaluate ONLY the [USER COMMAND] for routing. Use [RECENT CONVERSATION HISTORY] purely for context. "
            "If the new command contains MULTIPLE intents requiring tools outside Fast Brain, ALWAYS route to 'AGENTIC' and include all relevant domains in 'domains'.\n\n"
            "### FAST BRAIN RULES (ROUTE TO 'FAST' ONLY IF STRICTLY THESE)\n"
            "- Casual conversation, greetings, jokes, time, date, creator questions ('tumhe kisne banaya?'), or personal chit-chat.\n"
            "- Simple hardware controls: volume up/down/mute, brightness, screen lock, sleep, or screenshots.\n"
            "- Simple app/web launching or closing: 'Open Chrome', 'Close Notepad', 'Launch YouTube'.\n"
            "- Direct media playback: 'Play [song/video] on YouTube'.\n"
            "- Simple real-time web lookups: weather forecasts, live scores, quick definitions, or breaking news.\n"
            "- Simple factual 'How-to' queries: 'How to boil an egg', 'How to tie a tie'.\n\n"
            "### AGENTIC BRAIN RULES (ROUTE TO 'AGENTIC' IF REQUIRED)\n"
            "- Technical/Complex 'How-to' queries: 'How does my database work', 'How to code this script'.\n"
            "- Mobile Device Control & File Transfers.\n"
            "- Email, WhatsApp, or Telegram messaging.\n"
            "- File system CRUD operations or code writing/debugging.\n"
            "- Terminal commands, pip/npm, or git.\n"
            "- Long-term memory retrieval: searching personal facts, notes, vault, or calendar.\n"
            "- Advanced research: webpage scraping, arxiv search, YouTube transcript analysis, or deep research.\n"
            "- GUI screen clicking/automation, image generation/editing, or image/screen visual analysis.\n\n"
            "### FEW-SHOT EXAMPLES\n"
            "User: 'Hello Jarvis, tumhe kisne banaya hai?' -> {\"route\": \"FAST\", \"english_query\": \"who created jarvis\", \"domains\": [\"creator_identity\"]}\n"
            "User: 'Hi Jarvis, volume badha do' -> {\"route\": \"FAST\", \"english_query\": \"increase system volume\", \"domains\": [\"general_none\"]}\n"
            "User: 'Mera 7 din ka study plan banao' -> {\"route\": \"AGENTIC\", \"english_query\": \"create a 7 day study schedule plan\", \"domains\": [\"scheduling\"]}\n"
            "User: 'Jarvis, Kaif ko email bhej do ki main late aaunga' -> {\"route\": \"AGENTIC\", \"english_query\": \"send email to Kaif about being late\", \"domains\": [\"communication\"]}\n"
            "User: 'Mere liye ek portfolio dashboard banao' -> {\"route\": \"AGENTIC\", \"english_query\": \"build a portfolio web dashboard\", \"domains\": [\"ui_design\", \"coding\"]}\n"
            "User: 'Mere father ka naam kya hai?' -> {\"route\": \"AGENTIC\", \"english_query\": \"what is my father name\", \"domains\": [\"research_memory\"]}"
        )

        user_content = f"[RECENT CONVERSATION HISTORY]\n{trimmed_history}\n\n[USER COMMAND]\n\"{command}\""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
            "max_tokens": 200,
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
                data = self._safe_parse_json(raw_json)
                if not data:
                    logger.warning(f"Router Tier1 JSON unparseable | raw_preview='{str(raw_json)[:150]}'")
                    raise ValueError("Tier1 router JSON parse failed")
                parsed = self._parse_router_payload(data, command)
                logger.info(
                    f"[ROUTER_TELEMETRY] source=tier1 | latency_ms={latency_ms:.1f} | "
                    f"route={parsed['route']} | domains={parsed['domains']} | "
                    f"behavioral={parsed['domain']} | eng='{parsed['english_query'][:60]}' | "
                    f"cmd='{command[:80]}'"
                )
                return parsed
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
                        "max_tokens": 200,
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
                        data_fb = self._safe_parse_json(raw_json_fb)
                        if not data_fb:
                            logger.warning(f"Router Tier2 JSON unparseable | raw_preview='{str(raw_json_fb)[:150]}'")
                            raise ValueError("Tier2 router JSON parse failed")
                        parsed_fb = self._parse_router_payload(data_fb, command)
                        logger.info(
                            f"[ROUTER_TELEMETRY] source=tier2 | latency_ms={latency_ms_fb:.1f} | "
                            f"route={parsed_fb['route']} | domains={parsed_fb['domains']} | "
                            f"behavioral={parsed_fb['domain']} | eng='{parsed_fb['english_query'][:60]}' | "
                            f"cmd='{command[:80]}'"
                        )
                        return parsed_fb
                    else:
                        logger.warning(f"Tier 2 Router API non-200 status ({response_fb.status_code}): {response_fb.text[:100]}")
            except Exception as e2:
                logger.warning(f"Tier 2 Router API failed ({e2}). Switching to Local Regex Fallback (Tier 3).")

        return None

    def analyze_route(self, command: str, history_context: str = "") -> Optional[str]:
        res = self.analyze_route_full(command, history_context)
        return res["route"] if res else None


router_engine = GenericSemanticRouter()


def infer_local_domain(command: str) -> str:
    domains = infer_domains_from_command(command)
    return select_behavioral_domain(domains)


def get_local_fallback_route(command: str) -> str:
    cmd_lower = command.lower().strip()

    absolute_fast_patterns = [
        r'\b(volume|awaaz|sound|brightness|screenshot|lock|sleep|mute)\b',
        r'\b(open|kholo|close|band|start|launch)\b',
        r'\b(play|chalao|song|gana|music|youtube)\b',
        r'\b(weather|mausam|time|date|score|news|joke)\b',
        r'\b(hi|hello|hey|kaise ho|what is up|good morning|good evening)\b',
        r'\b(kisne banaya|who made you|who created you|tumhara creator)\b',
        r'^\s*(what is|kya hai|kya hota hai|who is|kaun hai)\s+\w+\s*$'
    ]

    agentic_strict_patterns = [
        r'\b(write|run|execute|create|make|generate|edit|banao|likho|chalao).{0,30}(python|rust|php|html|css|js|script|code|file|folder|dir|react|app|server|image|photo|picture|pic|wallpaper|logo|poster|art|illustration)\b',
        r'\b(image|photo|picture|pic|wallpaper|logo|poster|art|illustration).{0,30}(generate|create|make|edit|banao|bana do|bnado)\b',
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

    for pattern in agentic_strict_patterns:
        if re.search(pattern, cmd_lower):
            return "AGENTIC"

    for pattern in absolute_fast_patterns:
        if re.search(pattern, cmd_lower):
            return "FAST"

    action_words = re.findall(r'\b(and|aur|then|phir|baad mein)\b', cmd_lower)
    if len(action_words) > 0:
        return "AGENTIC"

    return "FAST"


def get_route_decision(command: str, memory_instance=None) -> str:
    if memory_instance and hasattr(memory_instance, "ephemeral"):
        if memory_instance.ephemeral.get("waiting_for_confirmation"):
            cmd_lower = command.lower().strip()
            confirm_pattern = r'\b(haa|ha|han|yes|yup|yeah|sure|ok|okay|bilkul|zaroor|theek hai|thik hai|do it|kar do|kardo|krdo|kar de|krde|bhej do|update kar do)\b'
            if re.search(confirm_pattern, cmd_lower):
                memory_instance.ephemeral["waiting_for_confirmation"] = False
                memory_instance.ephemeral["proactive_confirmed"] = True
                memory_instance.ephemeral["current_english_query"] = command
                memory_instance.ephemeral["current_domain"] = "general_none"
                memory_instance.ephemeral["active_domains"] = normalize_domains(None, command)
                logger.info("Proactive Confirmation detected -> Routing directly to AGENTIC")
                return "AGENTIC"
            else:
                if hasattr(memory_instance, "clear_pending_confirmation"):
                    memory_instance.clear_pending_confirmation()
                else:
                    memory_instance.ephemeral["waiting_for_confirmation"] = False
                    memory_instance.ephemeral.pop("pending_task_data", None)

    history_context = ""
    if memory_instance and hasattr(memory_instance, "get_fast_history_context"):
        try:
            history_context = memory_instance.get_fast_history_context()
        except Exception:
            history_context = ""

    cloud_result = router_engine.analyze_route_full(command, history_context)
    if cloud_result:
        if memory_instance and hasattr(memory_instance, "ephemeral"):
            memory_instance.ephemeral["current_english_query"] = cloud_result.get("english_query", command)
            memory_instance.ephemeral["current_domain"] = cloud_result.get("domain", "general_none")
            memory_instance.ephemeral["active_domains"] = cloud_result.get("domains", ["general_none"])
        return cloud_result["route"]

    logger.info("Using Local Rule-Based Fallback Router...")
    fallback_route = get_local_fallback_route(command)
    logger.info(
        f"[ROUTER_TELEMETRY] source=regex | route={fallback_route} | "
        f"cmd='{command[:80]}'"
    )
    if memory_instance and hasattr(memory_instance, "ephemeral"):
        local_domains = normalize_domains(None, command)
        memory_instance.ephemeral["current_english_query"] = command
        memory_instance.ephemeral["current_domain"] = select_behavioral_domain(local_domains)
        memory_instance.ephemeral["active_domains"] = local_domains
    return fallback_route


def fetch_hybrid_response(raw_command: str, memory_instance=None) -> Optional[Dict[str, any]]:
    try:
        decision = get_route_decision(raw_command, memory_instance)

        if decision == "AGENTIC":
            logger.info("Smart Router: AGENTIC (Deep Tasks, Memory, Comms & Visual Analysis)")
            context_blocks = []

            is_silent = False
            if memory_instance:
                if hasattr(memory_instance, "consume_silent_flag"):
                    is_silent = memory_instance.consume_silent_flag()
                elif hasattr(memory_instance, "ephemeral"):
                    is_silent = bool(memory_instance.ephemeral.pop("force_silent_agentic", False))

                if hasattr(memory_instance, "get_and_clear_feedback"):
                    memory_instance.get_and_clear_feedback()

                try:
                    logger.info("Fetching Initial Profile, Mood & Workspace Context...")
                    personal_context = memory_instance.get_relevant_context(raw_command)
                    if personal_context:
                        context_blocks.append(personal_context)
                except Exception as e:
                    logger.error(f"Memory Fetch Error: {e}")

                if hasattr(memory_instance, "ephemeral") and memory_instance.ephemeral.get("proactive_confirmed"):
                    pending_data = (
                        memory_instance.consume_pending_confirmation()
                        if hasattr(memory_instance, "consume_pending_confirmation")
                        else memory_instance.ephemeral.pop("pending_task_data", None)
                    )
                    memory_instance.ephemeral.pop("proactive_confirmed", None)
                    if isinstance(pending_data, dict):
                        proactive_block = (
                            "[CONFIRMED PROACTIVE TASK DETAILS]\n"
                            f"Original Proactive Instruction: {pending_data.get('agent_command', '')}\n"
                            f"Event Trigger Data:\n{pending_data.get('batched_data', '')}\n"
                            f"Question Asked to User: {pending_data.get('proactive_question', '')}\n"
                            "User has just confirmed this action. Execute the required tool now."
                        )
                        context_blocks.append(proactive_block)

            final_context = "\n".join(context_blocks)

            return run_agentic_loop(raw_command, final_context, memory_instance, silent=is_silent)
        else:
            logger.info("Smart Router: FAST (Direct Apps / Stateless Chat / Hardware)")

            if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
                cleared_feedback = memory_instance.get_and_clear_feedback()
                if cleared_feedback:
                    logger.info(f"Flushed pending live feedback: {cleared_feedback}")

            ephemeral = memory_instance.ephemeral if memory_instance and hasattr(memory_instance, "ephemeral") else None
            return fetch_from_groq(raw_command, memory_instance, ephemeral)

    except Exception as e:
        logger.error(f"Smart Router Error: {e}. Defaulting to Fast Brain.")

        if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
            memory_instance.get_and_clear_feedback()

        ephemeral = memory_instance.ephemeral if memory_instance and hasattr(memory_instance, "ephemeral") else None
        return fetch_from_groq(raw_command, memory_instance, ephemeral)


def process_command(raw_command: str, memory_instance=None) -> Dict[str, any]:
    resolved_command = resolve_pronouns(raw_command)
    result = fetch_hybrid_response(resolved_command, memory_instance)

    if not result:
        return make_result("Connection failed. Please check your internet connection.", priority="low")

    return result