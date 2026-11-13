import json
import os
import threading
import time
import re
import getpass
import socket
import subprocess
import platform
import sys
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
import openai
from core.logger.logger import logger
from core.brain.config import (
    LTM_EXTRACTION_API_KEY,
    LTM_EXTRACTION_MODEL,
    LTM_EXTRACTION_ENDPOINT,
    MEMORY_SUMMARY_API_KEY,
    MEMORY_SUMMARY_MODEL,
    MEMORY_SUMMARY_ENDPOINT,
    MEMORY_RAW_RETENTION_DAYS,
    MEMORY_SUMMARY_RETENTION_DAYS,
    MEMORY_SUMMARY_MIN_MESSAGES,
    MEMORY_SUMMARY_MAX_CATCHUP_DAYS,
    MEMORY_SUMMARY_CATCHUP_ON_STARTUP,
)


class ContextMemory:
    _LEADING_FILLERS = re.compile(
        r"^\s*(?:(?:jarvis|bhai|bro|sir|boss|hey|hi|hello|listen|sun|suno|dekh|dekho|please|plz|ek\s+kaam\s+kar(?:o|na)?)\b[\s,!.:-]*)+",
        re.IGNORECASE,
    )

    _COMMAND_PREFIXES = (
        "open ", "close ", "play ", "kholo", "band ", "send ", "bhej",
        "write ", "run ", "execute ", "search ", "find ", "check ",
        "screenshot", "lock ", "sleep ", "volume", "brightness",
        "email ", "whatsapp ", "telegram ", "message ", "create ", "make ", "banao",
        "fix ", "debug ", "install ", "delete ", "remove ", "analyze ", "explain ",
    )

    _QUESTION_STARTERS = re.compile(
        r"^\s*(?:kya|kab|kaise|kahan|kaun|kisne|kisko|kitna|kitne|kyu|kyun|"
        r"what|who|when|where|why|how|which|can\s+you|could\s+you|will\s+you|do\s+you|is\s+there|tell\s+me)\b",
        re.IGNORECASE,
    )

    _ONE_TIME_TASK_PATTERN = re.compile(
        r"\b(?:mere\s+liye|mujhe\s+ek|mera\s+ek|for\s+me|right\s+now|abhi\s+ke\s+liye|is\s+task\s+me)\b.*"
        r"\b(?:banao|bana\s+do|create|make|write|likho|likh\s+do|generate|send|bhej\s+do|check\s+karo|fix\s+karo)\b",
        re.IGNORECASE,
    )

    _EXPLICIT_PERMANENT_PATTERN = re.compile(
        r"\b(yaad\s*rakhna|remember\s*that|from\s*now\s*on|aage\s*se|hamesha|always|never|"
        r"kabhi\s*mat|kabhi\s*nahi|roz|rozana|daily|every\s*day|meri\s*aadat|usually|aksar)\b",
        re.IGNORECASE,
    )

    _SELF_PRONOUN_PATTERN = re.compile(
        r"\b(mai|main|mein|hum|mujhe|mera|meri|mere|hu|hun|i|my|me)\b",
        re.IGNORECASE,
    )

    _DURABLE_FACT_OR_HABIT_PATTERNS = [
        r"\b(roz|rozana|hamesha|aksar|usually|always|mostly|daily|every\s*day|every\s*morning|every\s*night|never|kabhi\s*nahi|kabhi\s*mat)\b",
        r"\b(pasand\s+hai|prefer|like\s+to|love\s+to|hate|dislike|routine|habit|aadat|favorite|favourite)\b",
        r"\b(yaad\s*rakhna|remember\s*that|from\s*now\s*on|aage\s*se)\b",
        r"\b(mera\s+naam|my\s+name|mera\s+bhai|meri\s+behen|mera\s+dost|mere\s+father|mere\s+papa|meri\s+mother|meri\s+mummy|my\s+(?:father|mother|sister|brother|friend|boss))\b",
        r"\b(rehta\s+hu|rehti\s+hu|live\s+in|padhta\s+hu|study\s+at|study\s+in|kaam\s+karta\s+hu|work\s+at|work\s+as|mera\s+number|mera\s+email|my\s+phone|my\s+email|my\s+laptop)\b",
        r"\b(?:\d{1,2}\s*(?:bje|bajey|baj|o'?clock|pm|am))\b.*\b(?:roz|daily|usually|aksar|hamesha|coding|study|sota|uthta|kaam)\b",
    ]

    def __init__(self, memory_path="Data/jarvis_memory"):
        self.memory_path = Path(memory_path)
        self.memory_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._extract_lock = threading.Lock()
        self.master_history_file = self.memory_path / "master_chat_history.jsonl"
        self.daily_summaries_file = self.memory_path / "daily_summaries.jsonl"
        old_json_file = self.memory_path / "master_chat_history.json"

        if old_json_file.exists() and not self.master_history_file.exists():
            old_data = self._load_json(old_json_file, [])
            self._rewrite_history_jsonl(self.master_history_file, old_data)
            try:
                os.remove(old_json_file)
            except Exception as e:
                logger.error(f"Failed to remove old json file: {e}")

        self.master_history = self._load_history_jsonl(self.master_history_file)
        self.daily_summaries = self._load_daily_summaries()
        self.last_message_date = self._get_last_message_date()
        self.ephemeral = {}
        self._ephemeral_expiry = {}
        self._devices_cache = []
        self._devices_cache_mtime = 0.0
        self._sys_info_cache = {}
        self._sys_info_expiry = {}
        self._net_info_cache = {}
        self._net_info_expiry = {}
        self.live_feedback_queue = []
        self.current_mode = "General Assistant"
        self.mode_timer = datetime.now()
        self._confirmation_timer = None
        self._summary_generation_lock = threading.Lock()

        try:
            self.ltm_client = openai.OpenAI(
                api_key=LTM_EXTRACTION_API_KEY,
                base_url=LTM_EXTRACTION_ENDPOINT,
            ) if LTM_EXTRACTION_API_KEY else None
        except Exception as e:
            logger.error(f"Failed to initialize LTM extraction client: {e}")
            self.ltm_client = None

        try:
            self.summary_client = openai.OpenAI(
                api_key=MEMORY_SUMMARY_API_KEY,
                base_url=MEMORY_SUMMARY_ENDPOINT,
            ) if MEMORY_SUMMARY_API_KEY else None
        except Exception as e:
            logger.error(f"Failed to initialize summary client: {e}")
            self.summary_client = None

        self._retry_queue_path = self.memory_path / "extraction_retry_queue.jsonl"
        self._retry_lock = threading.Lock()
        self._retry_queue = []
        try:
            self._retry_queue = self._load_retry_queue()
        except Exception as e:
            logger.error(f"Retry queue load failed at startup: {e}")

        self._start_retry_drainer()
        self._start_background_pruning()

    def _classify_message_priority(self, message: str) -> str:
        if self._is_hard_skip(message):
            return "skip"
        if self._is_force_include(message):
            return "force"
        return "llm"

    def _is_hard_skip(self, message: str) -> bool:
        if not message or not message.strip():
            return True

        low = message.lower().strip()
        cleaned = self._LEADING_FILLERS.sub("", low).strip()

        if not cleaned:
            return True

        if self._EXPLICIT_PERMANENT_PATTERN.search(cleaned):
            return False

        has_self_ref = bool(self._SELF_PRONOUN_PATTERN.search(cleaned))

        if re.match(
            r"^(hi|hello|hey|namaste|sup|whatsup|what'?s\s+up|hola|salam|good\s+(morning|evening|afternoon|night))[\s!?.,]*$",
            cleaned,
        ):
            return True

        if re.match(
            r"^(ok|okay|sure|cool|nice|thanks|thank\s+you|thik\s+hai|theek\s+hai|accha|acha|hmm|done|got\s+it|samajh\s+gaya|haan|han|nahi|yes|no|yeah|yup|nope|right|correct)[\s!?.,]*$",
            cleaned,
        ):
            return True

        command_verb_pattern = re.compile(
            r"\b(open|kholo|close|band|play|chalao|bajao|send|bhej\w*|write|likho|run|execute|search|find|check|screenshot|volume|brightness|lock|sleep|mute|unmute)\b",
            re.IGNORECASE,
        )

        if has_self_ref:
            return False

        if command_verb_pattern.search(cleaned):
            return True

        if self._QUESTION_STARTERS.search(cleaned):
            return True

        if any(cleaned.startswith(prefix) for prefix in self._COMMAND_PREFIXES):
            return True

        return True

    def _is_force_include(self, message: str) -> bool:
        if not message or not message.strip():
            return False

        raw_msg = message.strip()
        low = raw_msg.lower()
        cleaned = self._LEADING_FILLERS.sub("", low).strip()
        clean_raw = self._LEADING_FILLERS.sub("", raw_msg).strip()

        if not cleaned:
            return False

        is_question = bool(cleaned.endswith("?")) or bool(self._QUESTION_STARTERS.search(cleaned))
        if is_question:
            return False

        profile_pattern = re.compile(
            r"\b(mera|meri|mere|mere\s+paas|my)\s+"
            r"(naam|age|umar|email|mail|gmail|number|phone|mobile|contact|whatsapp|telegram|"
            r"instagram|handle|username|laptop|computer|pc|device|model|college|school|university|"
            r"city|shehar|gaon|village|job|kaam|profession|project|bhai|behen|dost|friend|"
            r"father|mother|papa|mummy|mom|dad|gf|bf|girlfriend|boyfriend|birthday|janamdin|"
            r"janmdin|anniversary|wife|husband|address|location|surname|sirname|nickname|"
            r"roll|aadhar|pan|id)\b",
            re.IGNORECASE,
        )

        identity_pattern = re.compile(
            r"\b(mai|main|mein|i\s+am|i'?m)\s+"
            r"(?:\d+\s+(?:saal|year|years)|.{0,40}?\b(?:developer|engineer|student|designer|coder|"
            r"freelancer|teacher|doctor|manager|writer|artist|programmer)\b)",
            re.IGNORECASE,
        )

        preference_pattern = re.compile(
            r"\b(mujhe|mujhko|mera|meri)\s+\w+\s+(pasand|nahi\s*pasand|prefer|like|love|hate|dislike)\b",
            re.IGNORECASE,
        )

        has_profile = bool(profile_pattern.search(cleaned))
        has_identity = bool(identity_pattern.search(cleaned))
        has_preference = bool(preference_pattern.search(cleaned))
        has_explicit_remember = bool(self._EXPLICIT_PERMANENT_PATTERN.search(cleaned))

        if has_profile or has_identity or has_preference:
            return True

        if has_explicit_remember:
            return False

        project_verb = re.search(
            r"\b(mai|main|mein)\s+(\S+)\s+(bana|bana\s+raha|bana\s+rahi|develop|building|build)\b",
            clean_raw,
            re.IGNORECASE,
        )
        if project_verb:
            entity = project_verb.group(2)
            if entity and entity[0].isupper() and entity.lower() not in {
                "ek", "a", "an", "ye", "yeh", "wo", "woh", "kuch",
            }:
                return True

        return False

    def _is_valid_triplet(self, src, rel, tgt):
        if not src or not rel or not tgt:
            return False
        src_clean = str(src).strip()
        tgt_clean = str(tgt).strip()
        rel_clean = str(rel).strip().lower()

        invalid_entities = {
            "agent", "info", "system", "jarvis", "data", "unknown",
            "yes", "no", "today", "tomorrow", "now", "thing", "stuff",
            "morning", "evening", "night", "afternoon", "subah", "raat", "shaam",
            "none", "null", "true", "false", "bhai", "sir", "bro",
        }
        if src_clean.lower() in invalid_entities or tgt_clean.lower() in invalid_entities:
            return False
        if len(src_clean) < 2 or len(tgt_clean) < 2:
            return False
        if src_clean.lower() == tgt_clean.lower():
            return False

        family_relations = {
            "father", "mother", "brother", "sister", "son",
            "daughter", "spouse", "uncle", "aunt",
        }
        if rel_clean in family_relations:
            if len(src_clean.split()) > 4 or len(tgt_clean.split()) > 4:
                return False

        ephemeral_or_behavioral_relations = {
            "is_doing", "eating", "going", "will_give", "must_remember",
            "status_update", "remember", "searching", "asking", "said",
            "talking_to", "wants_to", "planning_to", "habit", "has_habit",
            "routine", "has_routine", "daily_routine", "prefers_time",
            "works_at_time", "coding_time", "schedule",
        }
        if rel_clean in ephemeral_or_behavioral_relations:
            return False
        return True

    def set_pending_confirmation(self, task_data=None, ttl_seconds=90):
        with self._lock:
            if self._confirmation_timer:
                try:
                    self._confirmation_timer.cancel()
                except Exception as e:
                    logger.error(f"Error cancelling confirmation timer: {e}")
                self._confirmation_timer = None
            self.ephemeral["waiting_for_confirmation"] = True
            self.ephemeral.pop("proactive_confirmed", None)
            if task_data is not None:
                self.ephemeral["pending_task_data"] = task_data

            def _auto_expire():
                with self._lock:
                    self.ephemeral["waiting_for_confirmation"] = False
                    self.ephemeral.pop("proactive_confirmed", None)
                    self.ephemeral.pop("pending_task_data", None)
                    self._confirmation_timer = None

            self._confirmation_timer = threading.Timer(ttl_seconds, _auto_expire)
            self._confirmation_timer.daemon = True
            self._confirmation_timer.start()

    def clear_pending_confirmation(self):
        with self._lock:
            if self._confirmation_timer:
                try:
                    self._confirmation_timer.cancel()
                except Exception as e:
                    logger.error(f"Error cancelling confirmation timer: {e}")
                self._confirmation_timer = None
            self.ephemeral["waiting_for_confirmation"] = False
            self.ephemeral.pop("proactive_confirmed", None)
            self.ephemeral.pop("pending_task_data", None)

    def consume_pending_confirmation(self):
        with self._lock:
            if self._confirmation_timer:
                try:
                    self._confirmation_timer.cancel()
                except Exception as e:
                    logger.error(f"Error cancelling confirmation timer: {e}")
                self._confirmation_timer = None
            self.ephemeral["waiting_for_confirmation"] = False
            self.ephemeral.pop("proactive_confirmed", None)
            return self.ephemeral.pop("pending_task_data", None)

    def consume_silent_flag(self) -> bool:
        with self._lock:
            return bool(self.ephemeral.pop("force_silent_agentic", False))

    def set_last_artifact(self, key: str, file_path: str, ttl_seconds: int = 600):
        if not key or not file_path or not str(file_path).strip():
            return
        with self._lock:
            clean_path = str(file_path).strip()
            self.ephemeral[key] = clean_path
            self._ephemeral_expiry[key] = time.time() + ttl_seconds

    def _prune_expired_ephemeral(self):
        now = time.time()
        with self._lock:
            expired_keys = [
                k for k, exp_ts in list(self._ephemeral_expiry.items())
                if now >= exp_ts
            ]
            for k in expired_keys:
                self._ephemeral_expiry.pop(k, None)
                self.ephemeral.pop(k, None)

    def sync_connected_devices(self):
        with self._lock:
            try:
                devices_file = Path("Data/SessionCookies/connected_devices.json")
                if not devices_file.exists():
                    alt_file = Path(__file__).resolve().parents[3] / "Data" / "SessionCookies" / "connected_devices.json"
                    if alt_file.exists():
                        devices_file = alt_file

                if devices_file.exists():
                    mtime = devices_file.stat().st_mtime
                    if mtime != self._devices_cache_mtime:
                        with open(devices_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        self._devices_cache = data if isinstance(data, list) else []
                        self._devices_cache_mtime = mtime
                else:
                    self._devices_cache = []
                    self._devices_cache_mtime = 0.0

                if self._devices_cache:
                    self.ephemeral["connected_devices"] = list(self._devices_cache)
                else:
                    self.ephemeral.pop("connected_devices", None)
            except Exception as e:
                logger.warning(f"Failed to sync connected devices: {e}")

    def set_ml_ephemeral(self, ml_payload: dict, ttl_seconds: int = 600):
        if not isinstance(ml_payload, dict) or not ml_payload:
            return
        with self._lock:
            exp_ts = time.time() + ttl_seconds
            self.ephemeral["ml_prediction"] = dict(ml_payload)
            self.ephemeral["predicted_mood"] = ml_payload.get("mood", "")
            self.ephemeral["recommended_emotion"] = ml_payload.get("recommended_emotion", "")
            self.ephemeral["predicted_apps"] = list(ml_payload.get("likely_apps", []))
            self.ephemeral["predicted_tools"] = list(ml_payload.get("preferred_tools", []))
            for k in ("ml_prediction", "predicted_mood", "recommended_emotion", "predicted_apps", "predicted_tools"):
                self._ephemeral_expiry[k] = exp_ts

    def _prune_expired_sys_net_cache(self):
        now = time.time()
        with self._lock:
            for k in list(self._sys_info_expiry.keys()):
                if now >= self._sys_info_expiry[k]:
                    self._sys_info_cache.pop(k, None)
                    self._sys_info_expiry.pop(k, None)
            for k in list(self._net_info_expiry.keys()):
                if now >= self._net_info_expiry[k]:
                    self._net_info_cache.pop(k, None)
                    self._net_info_expiry.pop(k, None)

    def _gather_system_info(self) -> dict:
        self._prune_expired_sys_net_cache()
        with self._lock:
            cached = dict(self._sys_info_cache)
        needed = (
            "os_name", "os_release", "username", "hostname",
            "home", "desktop", "downloads", "timezone", "python",
        )
        if all(k in cached for k in needed):
            return cached

        fresh = {}
        try:
            fresh["os_name"] = platform.system() or "Unknown"
            fresh["os_release"] = platform.release() or ""
            fresh["username"] = getpass.getuser() or "unknown"
            fresh["hostname"] = platform.node() or "Unknown"
            home_path = Path.home()
            fresh["home"] = str(home_path).replace("\\", "/")
            fresh["desktop"] = str(home_path / "Desktop").replace("\\", "/")
            fresh["downloads"] = str(home_path / "Downloads").replace("\\", "/")
            try:
                fresh["timezone"] = str(datetime.now().astimezone().tzinfo)
            except Exception:
                fresh["timezone"] = "Unknown"
            fresh["python"] = ".".join(str(x) for x in sys.version_info[:2])
        except Exception as e:
            logger.warning(f"System info gather failed: {e}")

        now = time.time()
        with self._lock:
            for k, v in fresh.items():
                self._sys_info_cache[k] = v
                self._sys_info_expiry[k] = now + 3600
            cached = dict(self._sys_info_cache)
        return cached

    def _get_wifi_ssid(self) -> str:
        self._prune_expired_sys_net_cache()
        with self._lock:
            if "ssid" in self._net_info_cache:
                return self._net_info_cache["ssid"]

        ssid = None
        try:
            system = platform.system()
            if system == "Windows":
                try:
                    result = subprocess.run(
                        ["netsh", "wlan", "show", "interfaces"],
                        capture_output=True, text=True, timeout=3,
                        creationflags=0x08000000,
                    )
                    for line in result.stdout.splitlines():
                        if "SSID" in line and "BSSID" not in line:
                            parts = line.split(":", 1)
                            if len(parts) == 2:
                                candidate = parts[1].strip()
                                if candidate:
                                    ssid = candidate
                                    break
                except Exception:
                    pass
            elif system == "Linux":
                try:
                    result = subprocess.run(
                        ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                        capture_output=True, text=True, timeout=3,
                    )
                    for line in result.stdout.splitlines():
                        if line.startswith("yes:"):
                            ssid = line.split(":", 1)[1].strip()
                            break
                except Exception:
                    pass
            elif system == "Darwin":
                try:
                    result = subprocess.run(
                        ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
                        capture_output=True, text=True, timeout=3,
                    )
                    for line in result.stdout.splitlines():
                        if " SSID:" in line:
                            ssid = line.split("SSID:", 1)[1].strip()
                            break
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"WiFi detection failed: {e}")

        ssid = ssid or "Unknown"
        now = time.time()
        with self._lock:
            self._net_info_cache["ssid"] = ssid
            self._net_info_expiry["ssid"] = now + 30
        return ssid

    def _get_local_ip(self) -> str:
        self._prune_expired_sys_net_cache()
        with self._lock:
            if "ip" in self._net_info_cache:
                return self._net_info_cache["ip"]

        ip = "Unknown"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
        except Exception:
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = "Unknown"

        now = time.time()
        with self._lock:
            self._net_info_cache["ip"] = ip
            self._net_info_expiry["ip"] = now + 60
        return ip

    def _get_ltm_facts_block(self) -> str:
        try:
            from core.brain.Memory.LifetimeMemory import ltm_engine
            top_facts = ltm_engine.get_top_relations_for_user(limit=6)
            if top_facts:
                lines = ["[LTM_KNOWN_FACTS]"]
                for fact in top_facts:
                    lines.append(f"- {fact}")
                return "\n".join(lines)
        except Exception as e:
            logger.warning(f"LTM facts block error: {e}")
        return ""

    def get_ephemeral_context(self, mode: str = "agentic", current_command: str = "") -> str:
        with self._lock:
            self._prune_expired_ephemeral()
            self.sync_connected_devices()

            devices = self.ephemeral.get("connected_devices") or []
            english_query = self.ephemeral.get("current_english_query", "")
            domain = self.ephemeral.get("current_domain", "")
            waiting_confirm = bool(self.ephemeral.get("waiting_for_confirmation"))
            pending_data = self.ephemeral.get("pending_task_data") or {}
            current_mode = self.current_mode

        sys_info = self._gather_system_info()
        wifi_ssid = self._get_wifi_ssid()
        local_ip = self._get_local_ip()

        beh_block = ""
        try:
            if domain and domain != "general_none":
                from core.brain.Memory.BehavioralEngine import behavioral_pattern_engine
                beh_block = behavioral_pattern_engine.format_ephemeral_block(
                    current_command=current_command,
                    mode=mode,
                    english_query=english_query,
                    domain=domain,
                )
        except Exception as e:
            logger.error(f"Behavioral ephemeral inject error ({mode}): {e}")
            beh_block = ""

        ltm_block = self._get_ltm_facts_block()

        user_name = os.getenv("USER_NAME", "Sir")
        now = datetime.now()
        time_str = now.strftime("%A, %d %B %Y | %I:%M %p")
        tz_str = sys_info.get("timezone", "Unknown")
        os_line = f"{sys_info.get('os_name', 'Unknown')} {sys_info.get('os_release', '')}".strip()
        phones_str = ", ".join(str(d) for d in devices) if devices else "None"

        if waiting_confirm:
            pending_summary = None
            if isinstance(pending_data, dict):
                pending_summary = pending_data.get("proactive_question")
            confirm_str = pending_summary or "Active — awaiting user reply"
        else:
            confirm_str = "None"

        if mode == "fast":
            blocks = []
            blocks.append(
                f"[IDENTITY] User Name: {user_name} | Device: {sys_info.get('hostname', 'Unknown')}"
            )
            blocks.append(f"[SYSTEM_ENVIRONMENT] OS: {os_line}")
            blocks.append(f"[NETWORK] WiFi: {wifi_ssid} | Phones: {phones_str}")
            blocks.append(f"[RUNTIME] Time: {time_str} | Mode: {current_mode}")
            if beh_block:
                blocks.append(f"[BEHAVIORAL_PATTERNS]\n{beh_block}")
            if ltm_block:
                blocks.append(ltm_block)
            return "\n\n".join(blocks) + "\n"

        blocks = []
        blocks.append(
            "[IDENTITY]\n"
            f"- User Name: {user_name}\n"
            f"- OS Username: {sys_info.get('username', 'unknown')}\n"
            f"- Device: {sys_info.get('hostname', 'Unknown')}"
        )
        blocks.append(
            "[SYSTEM_ENVIRONMENT]\n"
            f"- OS: {os_line}\n"
            f"- Home: {sys_info.get('home', 'Unknown')}\n"
            f"- Desktop: {sys_info.get('desktop', 'Unknown')}\n"
            f"- Downloads: {sys_info.get('downloads', 'Unknown')}"
        )
        blocks.append(
            "[NETWORK]\n"
            f"- WiFi: {wifi_ssid}\n"
            f"- Local IP: {local_ip}\n"
            f"- Connected Phones: {phones_str}"
        )
        blocks.append(
            "[RUNTIME]\n"
            f"- Time: {time_str}\n"
            f"- Timezone: {tz_str}\n"
            f"- Mode: {current_mode}\n"
            f"- Pending Confirmation: {confirm_str}"
        )
        if beh_block:
            blocks.append(f"[BEHAVIORAL_PATTERNS — VERIFIED USER PREFERENCES]\n{beh_block}")
        if ltm_block:
            blocks.append(ltm_block)

        return "\n\n".join(blocks)

    def get_static_ephemeral_context(self, current_command: str = "") -> str:
        with self._lock:
            self._prune_expired_ephemeral()
            self.sync_connected_devices()
            english_query = self.ephemeral.get("current_english_query", "")
            domain = self.ephemeral.get("current_domain", "")

        sys_info = self._gather_system_info()

        beh_block = ""
        try:
            if domain and domain != "general_none":
                from core.brain.Memory.BehavioralEngine import behavioral_pattern_engine
                beh_block = behavioral_pattern_engine.format_ephemeral_block(
                    current_command=current_command,
                    mode="agentic",
                    english_query=english_query,
                    domain=domain,
                )
        except Exception as e:
            logger.error(f"Behavioral ephemeral inject error (static): {e}")
            beh_block = ""

        ltm_block = self._get_ltm_facts_block()

        os_line = f"{sys_info.get('os_name', 'Unknown')} {sys_info.get('os_release', '')}".strip()
        user_name = os.getenv("USER_NAME", "Sir")

        blocks = []
        blocks.append(
            "[IDENTITY]\n"
            f"- User Name: {user_name}\n"
            f"- OS Username: {sys_info.get('username', 'unknown')}\n"
            f"- Device: {sys_info.get('hostname', 'Unknown')}"
        )
        blocks.append(
            "[SYSTEM_ENVIRONMENT]\n"
            f"- OS: {os_line}\n"
            f"- Home: {sys_info.get('home', 'Unknown')}\n"
            f"- Desktop: {sys_info.get('desktop', 'Unknown')}\n"
            f"- Downloads: {sys_info.get('downloads', 'Unknown')}"
        )
        if beh_block:
            blocks.append(f"[BEHAVIORAL_PATTERNS — VERIFIED USER PREFERENCES]\n{beh_block}")
        if ltm_block:
            blocks.append(ltm_block)

        return "\n\n".join(blocks)

    def get_dynamic_ephemeral_context(self, current_command: str = "") -> str:
        with self._lock:
            self._prune_expired_ephemeral()
            self.sync_connected_devices()
            devices = self.ephemeral.get("connected_devices") or []
            waiting_confirm = bool(self.ephemeral.get("waiting_for_confirmation"))
            pending_data = self.ephemeral.get("pending_task_data") or {}
            current_mode = self.current_mode

        wifi_ssid = self._get_wifi_ssid()
        local_ip = self._get_local_ip()
        phones_str = ", ".join(str(d) for d in devices) if devices else "None"
        tz_str = self._gather_system_info().get("timezone", "Unknown")

        if waiting_confirm:
            pending_summary = None
            if isinstance(pending_data, dict):
                pending_summary = pending_data.get("proactive_question")
            confirm_str = pending_summary or "Active — awaiting user reply"
        else:
            confirm_str = "None"

        now = datetime.now()
        time_str = now.strftime("%A, %d %B %Y | %I:%M %p")

        ltm_block = self._get_ltm_facts_block()

        blocks = []
        blocks.append(
            "[NETWORK]\n"
            f"- WiFi: {wifi_ssid}\n"
            f"- Local IP: {local_ip}\n"
            f"- Connected Phones: {phones_str}"
        )
        blocks.append(
            "[RUNTIME]\n"
            f"- Time: {time_str}\n"
            f"- Timezone: {tz_str}\n"
            f"- Mode: {current_mode}\n"
            f"- Pending Confirmation: {confirm_str}"
        )
        if ltm_block:
            blocks.append(ltm_block)

        return "\n\n".join(blocks)

    def add_live_feedback(self, text):
        if text and text.strip():
            clean_text = text.strip()
            with self._lock:
                self.live_feedback_queue.append(clean_text)

    def get_and_clear_feedback(self):
        with self._lock:
            if not self.live_feedback_queue:
                return ""
            feedback = " | ".join(self.live_feedback_queue)
            self.live_feedback_queue.clear()
            return feedback

    def _load_json(self, file_path, default):
        try:
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return default
        except Exception as e:
            logger.error(f"Failed to load JSON from {file_path}: {e}")
            return default

    def _load_history_jsonl(self, file_path):
        history = []
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            history.append(json.loads(line))
            except Exception as e:
                logger.error(f"Failed to load JSONL from {file_path}: {e}")
        return history

    def _append_history_jsonl(self, file_path, entry):
        with self._lock:
            try:
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"Failed to append to JSONL {file_path}: {e}")

    def _rewrite_history_jsonl(self, file_path, data_list):
        with self._lock:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    for entry in data_list:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"Failed to rewrite JSONL {file_path}: {e}")

    def _load_daily_summaries(self):
        summaries = {}
        if self.daily_summaries_file.exists():
            try:
                with open(self.daily_summaries_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            date_key = entry.get("date")
                            if date_key:
                                summaries[date_key] = {
                                    "summary": entry.get("summary", ""),
                                    "message_count": entry.get("message_count", 0),
                                    "generated_at": entry.get("generated_at", ""),
                                }
            except Exception as e:
                logger.error(f"Failed to load daily summaries: {e}")
        return summaries

    def _save_daily_summary(self, date_str, summary, message_count):
        with self._lock:
            try:
                entry = {
                    "date": date_str,
                    "summary": summary,
                    "message_count": message_count,
                    "generated_at": datetime.now().isoformat(),
                }
                with open(self.daily_summaries_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self.daily_summaries[date_str] = {
                    "summary": summary,
                    "message_count": message_count,
                    "generated_at": entry["generated_at"],
                }
            except Exception as e:
                logger.error(f"Failed to save daily summary for {date_str}: {e}")

    def _rewrite_daily_summaries(self):
        with self._lock:
            try:
                with open(self.daily_summaries_file, "w", encoding="utf-8") as f:
                    for date_key in sorted(self.daily_summaries.keys()):
                        data = self.daily_summaries[date_key]
                        entry = {
                            "date": date_key,
                            "summary": data.get("summary", ""),
                            "message_count": data.get("message_count", 0),
                            "generated_at": data.get("generated_at", ""),
                        }
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"Failed to rewrite daily summaries: {e}")

    def _get_last_message_date(self):
        if not self.master_history:
            return datetime.now().strftime("%Y-%m-%d")
        try:
            last = self.master_history[-1]
            ts = datetime.fromisoformat(last.get("timestamp", ""))
            return ts.strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

    def _collect_messages_for_date(self, date_str):
        messages = []
        for msg in self.master_history:
            try:
                ts = datetime.fromisoformat(msg.get("timestamp", ""))
                if ts.strftime("%Y-%m-%d") == date_str:
                    messages.append(msg)
            except Exception:
                continue
        return messages

    def _generate_daily_summary(self, date_str, messages=None):
        if not self.summary_client:
            return None
        if date_str in self.daily_summaries:
            return self.daily_summaries[date_str].get("summary")

        with self._summary_generation_lock:
            if date_str in self.daily_summaries:
                return self.daily_summaries[date_str].get("summary")

            try:
                if messages is None:
                    messages = self._collect_messages_for_date(date_str)

                if len(messages) < MEMORY_SUMMARY_MIN_MESSAGES:
                    return None

                conversation_lines = []
                for msg in messages:
                    role = msg.get("role", "UNKNOWN")
                    message = msg.get("message", "")
                    if not message:
                        continue
                    conversation_lines.append(f"{role}: {message}")

                conversation_text = "\n".join(conversation_lines)
                if len(conversation_text) > 12000:
                    conversation_text = conversation_text[:12000] + "\n...[truncated]"

                prompt = (
                    f"You are summarizing one full day of conversation between a user and Jarvis (an AI assistant).\n"
                    f"Write a concise 2-4 sentence summary covering: key topics discussed, decisions made, important facts mentioned, and actions taken.\n"
                    f"Preserve important proper nouns exactly as they appear (people names, project names, place names).\n"
                    f"Respond in natural English/Hinglish (Roman script).\n"
                    f"Only include information clearly present in the conversation. Do not invent or infer.\n"
                    f"Output plain text only. No JSON, no markdown headers.\n\n"
                    f"Date: {date_str}\n\n"
                    f"Conversation:\n{conversation_text}\n\n"
                    f"Summary:"
                )

                response = self.summary_client.chat.completions.create(
                    model=MEMORY_SUMMARY_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a precise, faithful conversation summarizer. Output plain text only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=300,
                )

                summary = response.choices[0].message.content.strip()
                if not summary:
                    return None

                self._save_daily_summary(date_str, summary, len(messages))
                logger.info(f"Generated daily summary for {date_str} ({len(messages)} messages)")
                return summary

            except Exception as e:
                logger.error(f"Daily summary generation failed for {date_str}: {e}")
                return None

    def catchup_summaries(self):
        if not MEMORY_SUMMARY_CATCHUP_ON_STARTUP:
            return
        if not self.summary_client or not self.master_history:
            return
        try:
            today = datetime.now().date()
            day_groups = {}
            for msg in self.master_history:
                try:
                    ts = datetime.fromisoformat(msg.get("timestamp", ""))
                    msg_date = ts.date()
                    if msg_date < today:
                        day_key = msg_date.strftime("%Y-%m-%d")
                        day_groups.setdefault(day_key, []).append(msg)
                except Exception:
                    continue

            missing = []
            for day_key, msgs in day_groups.items():
                if day_key not in self.daily_summaries and len(msgs) >= MEMORY_SUMMARY_MIN_MESSAGES:
                    missing.append((day_key, msgs))

            missing.sort(key=lambda x: x[0])
            missing = missing[-MEMORY_SUMMARY_MAX_CATCHUP_DAYS:]

            if not missing:
                return

            logger.info(f"Memory catch-up: generating {len(missing)} missing daily summaries...")
            for day_key, msgs in missing:
                self._generate_daily_summary(day_key, msgs)
        except Exception as e:
            logger.error(f"Catchup summaries error: {e}")

    def _load_retry_queue(self):
        queue = []
        if not self._retry_queue_path.exists():
            return queue
        try:
            with open(self._retry_queue_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if isinstance(entry, dict) and entry.get("message"):
                            queue.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Retry queue load error: {e}")
        return queue

    def _save_retry_queue(self):
        with self._retry_lock:
            try:
                tmp_path = self._retry_queue_path.with_suffix(".jsonl.tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    for entry in self._retry_queue:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                os.replace(tmp_path, self._retry_queue_path)
            except Exception as e:
                logger.error(f"Retry queue save error: {e}")

    def _queue_for_retry(self, message, reason):
        if not message:
            return
        with self._retry_lock:
            for entry in self._retry_queue:
                if entry.get("message") == message:
                    entry["attempts"] = int(entry.get("attempts", 1))
                    entry["last_attempt"] = datetime.now().isoformat()
                    entry["reason"] = reason
                    self._save_retry_queue()
                    return
            self._retry_queue.append({
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "last_attempt": datetime.now().isoformat(),
                "attempts": 1,
                "reason": reason,
            })
            self._save_retry_queue()

    def _remove_from_retry_queue(self, message):
        with self._retry_lock:
            self._retry_queue = [e for e in self._retry_queue if e.get("message") != message]
            self._save_retry_queue()

    def _start_retry_drainer(self):
        def drain_loop():
            while True:
                time.sleep(300)
                try:
                    self._drain_retry_queue()
                except Exception as e:
                    logger.error(f"Retry drain error: {e}")

        threading.Thread(target=drain_loop, daemon=True).start()

    def _drain_retry_queue(self):
        with self._retry_lock:
            to_process = list(self._retry_queue)

        if not to_process:
            return

        logger.info(f"Draining extraction retry queue ({len(to_process)} items)...")

        remaining = []
        for entry in to_process:
            message = entry.get("message", "")
            attempts = int(entry.get("attempts", 1))
            reason = entry.get("reason", "unknown")

            if attempts >= 3:
                logger.warning(f"Dropping extraction retry (3 attempts exhausted): '{message[:80]}' | reason={reason}")
                continue

            try:
                result = self._extract_hybrid_memory_ai(message, is_force=True)
                ltm_saved = int(result.get("ltm_saved", 0)) if result else 0
                beh_saved = int(result.get("behavioral_saved", 0)) if result else 0
                if ltm_saved > 0 or beh_saved > 0:
                    logger.info(f"Retry extraction succeeded: '{message[:80]}'")
                    continue
            except Exception as e:
                logger.error(f"Retry extraction failed: {e}")

            entry["attempts"] = attempts + 1
            entry["last_attempt"] = datetime.now().isoformat()
            remaining.append(entry)

        with self._retry_lock:
            self._retry_queue = remaining
            self._save_retry_queue()

    def _async_extract_hybrid_memory(self, message):
        def _worker():
            try:
                result = self._extract_hybrid_memory_ai(message)
                if result and str(result.get("reason", "")).startswith("api_error"):
                    self._queue_for_retry(message, result.get("reason"))
            except Exception as e:
                logger.error(f"Async extraction worker failed: {e}")
                self._queue_for_retry(message, f"async_error: {str(e)[:150]}")

        try:
            threading.Thread(target=_worker, daemon=True).start()
        except Exception as e:
            logger.error(f"Hybrid memory thread starting error: {e}")
            self._queue_for_retry(message, f"thread_error: {str(e)[:150]}")

    def _sync_extract_and_verify(self, message):
        edges_before = -1
        patterns_before = -1

        try:
            from core.brain.Memory.LifetimeMemory import ltm_engine
            edges_before = ltm_engine.graph.number_of_edges()
        except Exception:
            pass

        try:
            from core.brain.Memory.BehavioralEngine import behavioral_pattern_engine
            patterns_before = len(behavioral_pattern_engine.patterns)
        except Exception:
            pass

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._extract_hybrid_memory_ai, message, True)

        result = None
        try:
            result = future.result(timeout=8.0)
        except concurrent.futures.TimeoutError:
            logger.warning(f"Force extraction timeout after 8s: '{message[:80]}'")
            self.ephemeral["extraction_failed"] = message
            self._queue_for_retry(message, "force_timeout")
            future.add_done_callback(lambda f: self._on_late_extraction(f, message))
            return False
        except Exception as e:
            logger.error(f"Force extraction raised: {e}")
            self.ephemeral["extraction_failed"] = message
            self._queue_for_retry(message, f"force_raised: {str(e)[:150]}")
            return False
        finally:
            executor.shutdown(wait=False)

        ltm_saved = int(result.get("ltm_saved", 0)) if result else 0
        beh_saved = int(result.get("behavioral_saved", 0)) if result else 0
        reason = (result.get("reason", "") if result else "") or ""
        skipped = bool(result.get("skipped", False)) if result else False

        edges_after = edges_before
        patterns_after = patterns_before

        try:
            from core.brain.Memory.LifetimeMemory import ltm_engine
            edges_after = ltm_engine.graph.number_of_edges()
        except Exception:
            pass

        try:
            from core.brain.Memory.BehavioralEngine import behavioral_pattern_engine
            patterns_after = len(behavioral_pattern_engine.patterns)
        except Exception:
            pass

        edges_delta = (edges_after - edges_before) if edges_before >= 0 else 0
        patterns_delta = (patterns_after - patterns_before) if patterns_before >= 0 else 0

        verified = (ltm_saved > 0) or (beh_saved > 0) or (edges_delta > 0) or (patterns_delta > 0)

        if verified:
            self.ephemeral.pop("extraction_failed", None)
            logger.info(
                f"Force extraction VERIFIED: ltm={ltm_saved} (delta_edges={edges_delta}) "
                f"behavioral={beh_saved} (delta_patterns={patterns_delta})"
            )
            return True

        if skipped:
            logger.warning(f"Force extraction skipped by LLM (reason={reason}): '{message[:80]}'")
        else:
            logger.warning(f"Force extraction completed empty: '{message[:80]}'")

        self.ephemeral["extraction_failed"] = message
        self._queue_for_retry(message, f"force_empty: {reason}")
        return False

    def _on_late_extraction(self, future, message):
        try:
            result = future.result(timeout=30)
            ltm_saved = int(result.get("ltm_saved", 0)) if result else 0
            beh_saved = int(result.get("behavioral_saved", 0)) if result else 0
            if ltm_saved > 0 or beh_saved > 0:
                logger.info(f"Late extraction succeeded for: '{message[:80]}'")
                if self.ephemeral.get("extraction_failed") == message:
                    self.ephemeral.pop("extraction_failed", None)
                    self._remove_from_retry_queue(message)
        except Exception as e:
            logger.warning(f"Late extraction failed: {e}")

    def _extract_hybrid_memory_ai(self, message, is_force=False):
        if not self.ltm_client:
            return {
                "ltm_saved": 0,
                "behavioral_saved": 0,
                "skipped": True,
                "reason": "no_ltm_client",
            }

        result = {
            "ltm_saved": 0,
            "behavioral_saved": 0,
            "skipped": False,
            "reason": "",
        }

        with self._extract_lock:
            recent_history = ""
            if self.master_history:
                recent_history = "\n".join([
                    f"{msg.get('role', '')}: {msg.get('message', '')}"
                    for msg in self.master_history[-6:]
                ])

            existing_nodes_str = "None"
            existing_relations_str = "None"
            try:
                from core.brain.Memory.LifetimeMemory import ltm_engine
                top_nodes = ltm_engine.get_all_node_names(limit=100)
                if top_nodes:
                    existing_nodes_str = ", ".join(top_nodes)

                top_relations = ltm_engine.get_all_relations(limit=50)
                if top_relations:
                    existing_relations_str = ", ".join(top_relations)
            except Exception as e:
                logger.error(f"Failed to fetch LTM nodes or relations: {e}")

            confidence_gate = 0.60 if is_force else 0.70

            prompt = f"""You are the Unified Hybrid Memory Extractor for Jarvis (an AI assistant).
Analyze the user's latest message using the recent conversation context and classify durable knowledge into TWO STRICTLY SEPARATE memory systems.

CRITICAL EXTRACTION RULES:
- Report your actual confidence between 0.0 and 1.0. Do NOT pre-filter based on confidence; the caller applies its own threshold.
- If the message is BOTH a task instruction AND contains a durable fact (name, relationship, entity, project, preference), STILL extract the durable fact. Set `is_current_task_instruction: true` to indicate immediate intent, but also set `has_ltm_facts` / `has_behavioral_patterns` appropriately and extract the content.
- Example: "Mera GhostVault project banao" -> `is_current_task_instruction: true`, `has_ltm_facts: true` (triplet: [User] --(DEVELOPS)--> [GhostVault]), `has_behavioral_patterns: false`.
- Questions and casual addressing ("bhai", "bro") are NOT facts. Never extract Jarvis as a brother or friend.
- Only extract durable knowledge that will still be true 6-12 months from now. Skip temporary moods or one-off plans.

SYSTEM 1: LTM GRAPH TRIPLETS (`ltm_triplets`) - Static entity facts:
- Always represent the user as the exact string "User" in `source`.
- Identity (name, age, city, college, profession), Relationships (family, friends), Assets (laptop model, phone, vehicle), Projects.
- HIGH PRIORITY — CONTACT INFO: Extract EVERY email address as `[User] --(HAS_EMAIL)--> [actual_email]` (is_singular=true). Extract EVERY phone number as `[User] --(HAS_PHONE)--> [actual_number]` (is_singular=true). If multiple emails or phones appear in the same message, emit ONE triplet per value.
- DEVICES: Laptop/PC/phone model goes as `[User] --(USES_LAPTOP)--> [Model]` or `[User] --(HAS_DEVICE)--> [Model]` (is_singular=true).
- Set `is_singular: true` for one-value relations (LIVES_IN, AGE, FATHER, MOTHER, WORKS_AT, HAS_PHONE, HAS_EMAIL, COLLEGE, USES_LAPTOP).
- If the message contains MULTIPLE distinct durable facts (e.g., device AND email AND phone), you MUST emit MULTIPLE triplets — one per fact. NEVER drop facts.

SYSTEM 2: BEHAVIORAL PATTERNS (`behavioral_patterns`) - Recurring habits and preferences:
- Time routines, coding/UI preferences, communication tone, workflow habits.
- Domain must be exactly one of: coding, scheduling, communication, ui_design, lifestyle.
- Topic must be normalized snake_case (e.g., ui_theme, code_comments, coding_schedule).
- Set `is_explicit_permanent: true` ONLY if user used words like "hamesha", "roz", "always", "never", "yaad rakhna".
- Write `meaning` and `trigger_contexts` in PURE ENGLISH.

[EXISTING GRAPH RELATIONS]: {existing_relations_str}
[EXISTING GRAPH NODES]: {existing_nodes_str}
[Recent Conversation Context]:
{recent_history if recent_history else 'No recent history.'}
[User's Latest Message]: "{message}"

Return STRICT JSON:
{{
  "reasoning": "Brief explanation",
  "is_current_task_instruction": boolean,
  "has_ltm_facts": boolean,
  "ltm_triplets": [
    {{
      "source": "User",
      "relation": "UPPERCASE_RELATION",
      "target": "Entity",
      "is_singular": boolean,
      "metadata": {{
        "confidence": 0.0,
        "context": "Brief context",
        "source_message": "User snippet"
      }},
      "inverse": {{
        "relation": "INVERSE_RELATION",
        "target": "User"
      }}
    }}
  ],
  "has_behavioral_patterns": boolean,
  "behavioral_patterns": [
    {{
      "type": "routine|preference|habit|dislike",
      "domain": "coding|scheduling|communication|ui_design|lifestyle",
      "topic": "snake_case_slot",
      "is_explicit_permanent": boolean,
      "raw_statement": "Verbatim user quote",
      "meaning": "Pure English interpretation",
      "trigger_contexts": "4-6 scenarios",
      "confidence": 0.0
    }}
  ]
}}"""

            last_error = None

            for attempt in range(3):
                try:
                    response = self.ltm_client.chat.completions.create(
                        model=LTM_EXTRACTION_MODEL,
                        messages=[
                            {"role": "system", "content": "You are a precise hybrid memory extraction engine. Output strictly valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.0,
                        max_tokens=800,
                        response_format={"type": "json_object"},
                    )
                    raw_text = response.choices[0].message.content.strip()
                    clean_text = re.sub(r"^```json\n|```$", "", raw_text, flags=re.MULTILINE).strip()
                    data = json.loads(clean_text)

                    is_task = data.get("is_current_task_instruction") is True

                    logger.info(
                        f"Hybrid Extraction | task={is_task} | "
                        f"LTM={data.get('has_ltm_facts')} ({len(data.get('ltm_triplets', []))}) | "
                        f"Behavioral={data.get('has_behavioral_patterns')} ({len(data.get('behavioral_patterns', []))})"
                    )

                    if data.get("has_ltm_facts") is True:
                        triplets = data.get("ltm_triplets", []) or []
                        try:
                            from core.brain.Memory.LifetimeMemory import ltm_engine
                            for t in triplets:
                                if not isinstance(t, dict):
                                    continue
                                src = str(t.get("source", "")).strip()
                                rel = str(t.get("relation", "")).strip().upper()
                                tgt = str(t.get("target", "")).strip()
                                is_singular = bool(t.get("is_singular", False))
                                metadata = t.get("metadata", {}) or {}
                                try:
                                    conf = float(metadata.get("confidence", 0.0))
                                except (ValueError, TypeError):
                                    conf = 0.0
                                inverse = t.get("inverse")

                                if conf < confidence_gate:
                                    logger.debug(f"LTM Triplet rejected (conf={conf:.2f} < {confidence_gate}): [{src}] --({rel})--> [{tgt}]")
                                    continue

                                if not self._is_valid_triplet(src, rel, tgt):
                                    logger.debug(f"LTM Triplet invalid: [{src}] --({rel})--> [{tgt}]")
                                    continue

                                valid_inverse = None
                                if isinstance(inverse, dict):
                                    inv_rel = str(inverse.get("relation", "")).strip().upper()
                                    inv_tgt = str(inverse.get("target") or src).strip()
                                    if self._is_valid_triplet(tgt, inv_rel, inv_tgt):
                                        valid_inverse = {"relation": inv_rel, "target": inv_tgt}

                                ltm_engine.record_triplet(
                                    src, rel, tgt,
                                    metadata=metadata,
                                    inverse=valid_inverse,
                                    is_singular=is_singular,
                                )
                                result["ltm_saved"] += 1
                                logger.info(f"LTM Saved: [{src}] --({rel})--> [{tgt}] (conf={conf:.2f})")
                        except Exception as e:
                            logger.error(f"LTM Engine Save Error: {e}")

                    if data.get("has_behavioral_patterns") is True:
                        patterns = data.get("behavioral_patterns", []) or []
                        try:
                            from core.brain.Memory.BehavioralEngine import behavioral_pattern_engine
                            for p in patterns:
                                if not isinstance(p, dict):
                                    continue
                                try:
                                    p_conf = float(p.get("confidence", 0.0))
                                except (ValueError, TypeError):
                                    p_conf = 0.0
                                if p_conf < confidence_gate:
                                    continue

                                is_exp_perm = bool(p.get("is_explicit_permanent", False))
                                if is_task and not is_exp_perm:
                                    logger.debug(f"Skipping non-permanent behavioral from task: {p.get('meaning', '')[:60]}")
                                    continue

                                if not p.get("raw_statement"):
                                    p["raw_statement"] = message.strip()

                                behavioral_pattern_engine._upsert_pattern(p)
                                result["behavioral_saved"] += 1
                        except Exception as e:
                            logger.error(f"Behavioral Engine Save Error: {e}")

                    return result

                except Exception as e:
                    last_error = e
                    logger.error(f"Hybrid Memory API error (attempt {attempt + 1}/3): {e}")
                    if attempt < 2:
                        time.sleep(1)

            result["reason"] = f"api_error: {str(last_error)[:200]}" if last_error else "api_error"
            if is_force:
                raise RuntimeError(result["reason"])
            return result

    def _start_background_pruning(self):
        try:
            threading.Thread(target=self._prune_old_messages, daemon=True).start()
            timer = threading.Timer(86400, self._start_background_pruning)
            timer.daemon = True
            timer.start()
        except Exception as e:
            logger.error(f"Pruning timer error: {e}")

    def _prune_old_messages(self):
        with self._lock:
            if not self.master_history:
                return
            history_snapshot = list(self.master_history)

        try:
            now = datetime.now()
            raw_cutoff = now - timedelta(days=MEMORY_RAW_RETENTION_DAYS)
            summary_cutoff = now - timedelta(days=MEMORY_SUMMARY_RETENTION_DAYS)

            day_groups = {}
            for msg in history_snapshot:
                try:
                    ts = datetime.fromisoformat(msg.get("timestamp", now.isoformat()))
                    if ts < raw_cutoff:
                        day_key = ts.strftime("%Y-%m-%d")
                        day_groups.setdefault(day_key, []).append(msg)
                except Exception:
                    continue

            for day_key, msgs in day_groups.items():
                if day_key not in self.daily_summaries and len(msgs) >= MEMORY_SUMMARY_MIN_MESSAGES:
                    self._generate_daily_summary(day_key, msgs)

            with self._lock:
                filtered_history = []
                for msg in self.master_history:
                    try:
                        msg_time = datetime.fromisoformat(msg.get("timestamp", now.isoformat()))
                        if msg_time >= raw_cutoff:
                            filtered_history.append(msg)
                    except Exception:
                        continue

                if len(filtered_history) < len(self.master_history):
                    removed = len(self.master_history) - len(filtered_history)
                    self.master_history = filtered_history
                    self._rewrite_history_jsonl(self.master_history_file, self.master_history)
                    logger.info(f"Pruned {removed} raw messages older than {MEMORY_RAW_RETENTION_DAYS} days")

            self._prune_old_summaries(summary_cutoff)
        except Exception as e:
            logger.error(f"Pruning history error: {e}")

    def _prune_old_summaries(self, cutoff):
        to_remove = []
        for date_key in list(self.daily_summaries.keys()):
            try:
                day = datetime.strptime(date_key, "%Y-%m-%d")
                if day < cutoff:
                    to_remove.append(date_key)
            except Exception:
                continue

        if not to_remove:
            return

        for key in to_remove:
            del self.daily_summaries[key]
        self._rewrite_daily_summaries()
        logger.info(f"Pruned {len(to_remove)} daily summaries older than {MEMORY_SUMMARY_RETENTION_DAYS} days")

    def _track_session_state(self, message):
        try:
            if (datetime.now() - self.mode_timer).total_seconds() / 60 > 30:
                self.current_mode = "General Assistant"
            msg_lower = message.lower()
            if any(w in msg_lower for w in ["code", "python", "error", "bug", "script", "terminal", "git"]):
                self.current_mode = "Technical"
                self.mode_timer = datetime.now()
            elif any(w in msg_lower for w in ["joke", "song", "play", "movie"]):
                self.current_mode = "Casual"
                self.mode_timer = datetime.now()
        except Exception as e:
            logger.error(f"Session state error: {e}")

    def add_message(self, role, message, metadata=None):
        if not message or not message.strip():
            return
        try:
            if metadata and isinstance(metadata, dict):
                for key, value in metadata.items():
                    if isinstance(value, str) and len(value) > 2000:
                        metadata[key] = value[:2000] + "\n\n[...Data Truncated to save Memory]"

            now = datetime.now()
            today_key = now.strftime("%Y-%m-%d")

            new_entry = {
                "role": role,
                "message": message,
                "timestamp": now.isoformat(),
            }
            if metadata:
                new_entry["metadata"] = metadata

            with self._lock:
                self.master_history.append(new_entry)

            self._append_history_jsonl(self.master_history_file, new_entry)

            if self.last_message_date != today_key:
                old_date = self.last_message_date
                self.last_message_date = today_key
                if old_date and old_date not in self.daily_summaries:
                    threading.Thread(
                        target=self._generate_daily_summary,
                        args=(old_date,),
                        daemon=True,
                    ).start()

            ignore_words = [
                "ok", "okay", "yes", "no", "thanks", "thank you", "clear",
                "done", "nice", "cool", "hmm", "acha",
            ]

            if role == "USER" and message.lower().strip() not in ignore_words:
                self._track_session_state(message)

                try:
                    priority = self._classify_message_priority(message)
                except Exception as e:
                    logger.error(f"Priority classification failed, defaulting to async: {e}")
                    priority = "llm"

                if priority == "skip":
                    logger.debug(f"Memory extraction SKIP (hard filter): '{message[:80]}'")
                elif priority == "force":
                    logger.info(f"Memory extraction FORCE (sync + verify): '{message[:80]}'")
                    self._sync_extract_and_verify(message)
                else:
                    self._async_extract_hybrid_memory(message)
        except Exception as e:
            logger.error(f"Error adding message to memory: {e}")

    def _format_entry(self, entry, dt):
        time_str = dt.strftime("%d %b, %H:%M")
        role = entry.get("role", "UNKNOWN")
        message = entry.get("message", "")
        metadata = entry.get("metadata", {})

        if role == "CONVERSATION":
            block = f"[{time_str}]\n{message}"
        else:
            block = f"[{time_str}]\n<{role.capitalize()}>\n{message}"

        if metadata:
            log_content = []
            apps_opened = metadata.get("apps_opened", [])
            apps_closed = metadata.get("apps_closed", [])
            files_touched = metadata.get("files_touched", [])
            system_events = metadata.get("system_events", [])
            if apps_opened or apps_closed or files_touched or system_events:
                log_content.append("  ACTIONS TAKEN:")
                if apps_opened:
                    log_content.append(f"  - Opened Apps: {', '.join(apps_opened)}")
                if apps_closed:
                    log_content.append(f"  - Closed Apps: {', '.join(apps_closed)}")
                if files_touched:
                    log_content.append(f"  - Files Touched: {', '.join(files_touched)}")
                for evt in system_events:
                    log_content.append(f"  - System: {evt}")
            if log_content:
                xml_log = "\n<System_Execution_Log>\n" + "\n".join(log_content).strip() + "\n</System_Execution_Log>"
                block += xml_log

        if role != "CONVERSATION":
            block += f"\n</{role.capitalize()}>"
        return block

    def get_fast_history_context(self):
        with self._lock:
            if not self.master_history:
                return "No recent conversation."
            recent_entries = list(self.master_history[-10:])
        try:
            history_str = []
            for entry in recent_entries:
                time_str = datetime.fromisoformat(entry.get("timestamp", datetime.now().isoformat())).strftime("%H:%M")
                if entry.get("role") == "CONVERSATION":
                    line = f"[{time_str}] {entry.get('message', '')}"
                else:
                    line = f"[{time_str}] {entry.get('role', 'UNKNOWN')}: {entry.get('message', '')}"
                metadata = entry.get("metadata", {})
                if isinstance(metadata, dict):
                    meta_parts = []
                    if metadata.get("apps_opened"):
                        meta_parts.append(f"Opened: {', '.join(metadata['apps_opened'])}")
                    if metadata.get("apps_closed"):
                        meta_parts.append(f"Closed: {', '.join(metadata['apps_closed'])}")
                    if metadata.get("files_touched"):
                        meta_parts.append(f"Files: {', '.join(metadata['files_touched'])}")
                    if metadata.get("system_events"):
                        meta_parts.append(f"Events: {'; '.join(metadata['system_events'][:3])}")
                    if meta_parts:
                        line += f" [Actions: {' | '.join(meta_parts)}]"
                history_str.append(line)
            return "\n".join(history_str)
        except Exception as e:
            logger.error(f"Context retrieval error: {e}")
            return "Error retrieving history."

    def get_agentic_fast_context(self):
        with self._lock:
            if not self.master_history:
                return "<Recent_Context>\nNo recent conversation.\n</Recent_Context>"
            recent_entries = list(self.master_history[-10:])
        try:
            history_lines = ["<Recent_Context>"]
            for entry in recent_entries:
                dt = datetime.fromisoformat(entry.get("timestamp", datetime.now().isoformat()))
                time_str = dt.strftime("%H:%M")
                role = entry.get("role", "UNKNOWN")
                message = entry.get("message", "")
                metadata = entry.get("metadata", {})
                if role == "CONVERSATION":
                    block = f"[{time_str}]\n{message}"
                else:
                    block = f"[{time_str}]\n<{role.capitalize()}>\n{message}"
                if metadata:
                    log_content = []
                    apps_opened = metadata.get("apps_opened", [])
                    apps_closed = metadata.get("apps_closed", [])
                    files_touched = metadata.get("files_touched", [])
                    system_events = metadata.get("system_events", [])
                    if apps_opened or apps_closed or files_touched or system_events:
                        log_content.append("  ACTIONS TAKEN:")
                        if apps_opened:
                            log_content.append(f"  - Opened Apps: {', '.join(apps_opened)}")
                        if apps_closed:
                            log_content.append(f"  - Closed Apps: {', '.join(apps_closed)}")
                        if files_touched:
                            log_content.append(f"  - Files Touched: {', '.join(files_touched)}")
                        for evt in system_events:
                            log_content.append(f"  - System: {evt}")
                        log_content.append("")
                    if log_content:
                        xml_log = "\n<System_Execution_Log>\n" + "\n".join(log_content).strip() + "\n</System_Execution_Log>"
                        block += xml_log
                if role != "CONVERSATION":
                    block += f"\n</{role.capitalize()}>"
                history_lines.append(block)
            history_lines.append("</Recent_Context>")
            return "\n\n".join(history_lines)
        except Exception as e:
            logger.error(f"Agent context retrieval error: {e}")
            return "<Recent_Context>\nError retrieving history.\n</Recent_Context>"

    def get_chat_history_for_tool(self, query=None):
        try:
            today = datetime.now().date()
            raw_cutoff = today - timedelta(days=MEMORY_RAW_RETENTION_DAYS)
            raw_cutoff_str = raw_cutoff.strftime("%Y-%m-%d")

            query_terms = []
            if query and isinstance(query, str):
                query_terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]

            def matches(text):
                if not query_terms:
                    return True
                text_lower = str(text).lower()
                return any(term in text_lower for term in query_terms)

            recent_blocks = []
            for entry in self.master_history:
                try:
                    ts = datetime.fromisoformat(entry.get("timestamp", ""))
                    date_key = ts.strftime("%Y-%m-%d")
                    if date_key >= raw_cutoff_str:
                        message = entry.get("message", "")
                        if matches(message):
                            recent_blocks.append(self._format_entry(entry, ts))
                except Exception:
                    continue

            summary_blocks = []
            for date_key in sorted(self.daily_summaries.keys()):
                if date_key < raw_cutoff_str:
                    summary = self.daily_summaries[date_key].get("summary", "")
                    if matches(summary):
                        summary_blocks.append(f"[{date_key}]\n{summary}")

            if not recent_blocks and not summary_blocks:
                return "No matching conversation history found in the last 15 days."

            parts = []
            if recent_blocks:
                parts.append(
                    f"=== RECENT MESSAGES (last {MEMORY_RAW_RETENTION_DAYS} days) ===\n"
                    + "\n\n".join(recent_blocks)
                )
            if summary_blocks:
                parts.append(
                    f"=== DAILY SUMMARIES (older days, up to {MEMORY_SUMMARY_RETENTION_DAYS} days) ===\n"
                    + "\n\n".join(summary_blocks)
                )
            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"History for tool retrieval error: {e}")
            return "Error retrieving conversation history."