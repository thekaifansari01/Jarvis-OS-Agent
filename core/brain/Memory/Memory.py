import json
import os
import threading
import time
import re
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
    def __init__(self, memory_path="Data/jarvis_memory"):
        self.memory_path = Path(memory_path)
        self.memory_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
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

        self._start_background_pruning()

    def _is_valid_triplet(self, src, rel, tgt):
        invalid_entities = {
            "agent", "info", "system", "jarvis", "data", "unknown",
            "yes", "no", "today", "tomorrow", "now", "thing", "stuff"
        }
        if src.lower() in invalid_entities or tgt.lower() in invalid_entities:
            return False
        if len(src) < 2 or len(tgt) < 2:
            return False
        if src.lower() == tgt.lower():
            return False

        family_relations = {
            "father", "mother", "brother", "sister", "son",
            "daughter", "spouse", "uncle", "aunt"
        }
        if rel.lower() in family_relations:
            if len(src.split()) > 3 or len(tgt.split()) > 3:
                return False

        ephemeral_relations = {
            "is_doing", "eating", "going", "will_give", "must_remember",
            "status_update", "remember", "searching", "asking", "said",
            "talking_to", "wants_to", "planning_to"
        }
        if rel.lower() in ephemeral_relations:
            return False
        return True

    def set_pending_confirmation(self, task_data=None, ttl_seconds=60):
        with self._lock:
            if self._confirmation_timer:
                try:
                    self._confirmation_timer.cancel()
                except Exception as e:
                    logger.error(f"Error cancelling confirmation timer: {e}")
                self._confirmation_timer = None
            self.ephemeral["waiting_for_confirmation"] = True
            if task_data:
                self.ephemeral["pending_task_data"] = task_data

            def _auto_expire():
                with self._lock:
                    self.ephemeral["waiting_for_confirmation"] = False
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
            self.ephemeral.pop("pending_task_data", None)

    def add_live_feedback(self, text):
        if text and text.strip():
            self.live_feedback_queue.append(text.strip())

    def get_and_clear_feedback(self):
        if not self.live_feedback_queue:
            return ""
        feedback = " | ".join(self.live_feedback_queue)
        self.live_feedback_queue.clear()
        return feedback

    def _load_json(self, file_path, default):
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return default
        except Exception as e:
            logger.error(f"Failed to load JSON from {file_path}: {e}")
            return default

    def _load_history_jsonl(self, file_path):
        history = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            history.append(json.loads(line))
            except Exception as e:
                logger.error(f"Failed to load JSONL from {file_path}: {e}")
        return history

    def _append_history_jsonl(self, file_path, entry):
        with self._lock:
            try:
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"Failed to append to JSONL {file_path}: {e}")

    def _rewrite_history_jsonl(self, file_path, data_list):
        with self._lock:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for entry in data_list:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"Failed to rewrite JSONL {file_path}: {e}")

    def _load_daily_summaries(self):
        summaries = {}
        if self.daily_summaries_file.exists():
            try:
                with open(self.daily_summaries_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            date_key = entry.get('date')
                            if date_key:
                                summaries[date_key] = {
                                    "summary": entry.get('summary', ''),
                                    "message_count": entry.get('message_count', 0),
                                    "generated_at": entry.get('generated_at', '')
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
                    "generated_at": datetime.now().isoformat()
                }
                with open(self.daily_summaries_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self.daily_summaries[date_str] = {
                    "summary": summary,
                    "message_count": message_count,
                    "generated_at": entry["generated_at"]
                }
            except Exception as e:
                logger.error(f"Failed to save daily summary for {date_str}: {e}")

    def _rewrite_daily_summaries(self):
        with self._lock:
            try:
                with open(self.daily_summaries_file, 'w', encoding='utf-8') as f:
                    for date_key in sorted(self.daily_summaries.keys()):
                        data = self.daily_summaries[date_key]
                        entry = {
                            "date": date_key,
                            "summary": data.get("summary", ""),
                            "message_count": data.get("message_count", 0),
                            "generated_at": data.get("generated_at", "")
                        }
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"Failed to rewrite daily summaries: {e}")

    def _get_last_message_date(self):
        if not self.master_history:
            return datetime.now().strftime("%Y-%m-%d")
        try:
            last = self.master_history[-1]
            ts = datetime.fromisoformat(last.get('timestamp', ''))
            return ts.strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

    def _collect_messages_for_date(self, date_str):
        messages = []
        for msg in self.master_history:
            try:
                ts = datetime.fromisoformat(msg.get('timestamp', ''))
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
                    role = msg.get('role', 'UNKNOWN')
                    message = msg.get('message', '')
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
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    max_tokens=300
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
                    ts = datetime.fromisoformat(msg.get('timestamp', ''))
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

    def _async_extract_permanent_facts(self, message):
        try:
            thread = threading.Thread(target=self._extract_permanent_facts_ai, args=(message,))
            thread.daemon = True
            thread.start()
        except Exception as e:
            logger.error(f"Thread starting error: {e}")

    def _extract_permanent_facts_ai(self, message):
        if not self.ltm_client or len(message.split()) < 2:
            return

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

        prompt = f"""You are the core LTM (Lifetime Memory) Engine for Jarvis.
Your job is to analyze the user's latest message using the context of the recent conversation, and extract ONLY permanent, long-lasting factual knowledge into a Graph structure.

[CRITICAL GUARDRAILS]:
1. ZERO-HALLUCINATION: If the message does not contain a CLEAR, UNDENIABLE permanent fact, you MUST return "is_permanent_fact": false. Do not guess, infer, or force a relation.
2. THE 1-YEAR TEST: Will this fact likely still be true or relevant 1 years from now? If 'No' (e.g., current mood, current task, upcoming trip), IGNORE it entirely and return false.

[WHAT TO SAVE]:
- Identity & Traits (Profession, Age, Habits, Skills).
- Relationships (Friends, Family, Colleagues).
- Hard Preferences (Likes, Dislikes, Allergies, Favorite things).
- Assets (Car owned, Phone model, Pets).
- Contact Information (Phone numbers, Emails, Addresses).

[EXISTING GRAPH RELATIONS]:
{existing_relations_str}

[EXTRACTION RULES]:
1. REUSE RELATIONS FIRST: Look at the [EXISTING GRAPH RELATIONS] list above. If an exact or highly similar relation already exists, YOU MUST USE IT (e.g., if FATHER is there, use it).
2. INVENTING RELATIONS: If no suitable relation exists, you are free to invent a new one. The new relation MUST be UPPERCASE, strictly 1-3 words, and represent a permanent state (e.g., LIKES, OWNS, WORKS_AS).
3. ENTITY VS ATTRIBUTE (CRITICAL): If the target is an attribute like a phone number, email address, or age, DO NOT make the relation a number (e.g. 9927272822). Use a general property relation like HAS_CONTACT, HAS_PHONE, HAS_EMAIL, or HAS_AGE, and put the actual data in the "target".
4. NODE REUSE: Check the [EXISTING GRAPH NODES] below. If the concept exists, use the EXACT matching node name.
5. ENTITY NORMALIZATION: Keep entities short (1-3 words max) and in Title Case. Strip all articles (A, An, The).
6. PRONOUN RESOLUTION: Resolve pronouns (he/she/it) using the Context History. Replace pronouns with actual entity names.
7. CONFLICT RESOLUTION: If a new fact contradicts an existing node in the graph, extract the NEW fact and explicitly explain the override in your reasoning.

[EXISTING GRAPH NODES]:
{existing_nodes_str}

[Context History]:
{recent_history if recent_history else 'No recent history.'}

[User's Latest Message]: "{message}"

Return STRICT JSON exactly in this schema:
{{
    "reasoning": "Explain why this passes the 1-Year Test and why you chose/invented this relation.",
    "is_permanent_fact": boolean,
    "triplets": [
        {{
            "source": "Entity1",
            "relation": "YOUR_RELATION",
            "target": "Entity2",
            "metadata": {{
                "confidence": float,
                "context": "Brief context about this relation",
                "source_message": "Exact sentence or snippet proving this fact"
            }},
            "inverse": {{
                "relation": "INVERSE_RELATION_NAME",
                "target": "Entity1"
            }}
        }}
    ]
}}
"""
        for _ in range(3):
            try:
                response = self.ltm_client.chat.completions.create(
                    model=LTM_EXTRACTION_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a precise, autonomous knowledge graph extraction engine. Output strictly valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
                raw_text = response.choices[0].message.content.strip()
                clean_text = re.sub(r'^```json\n|```$', '', raw_text, flags=re.MULTILINE).strip()
                data = json.loads(clean_text)

                if data.get("is_permanent_fact") is True:
                    triplets = data.get("triplets", [])
                    if triplets:
                        try:
                            from core.brain.Memory.LifetimeMemory import ltm_engine
                            for t in triplets:
                                src = str(t.get("source", "")).strip().title()
                                rel = str(t.get("relation", "")).strip().upper()
                                tgt = str(t.get("target", "")).strip().title()
                                metadata = t.get("metadata", {})
                                inverse = t.get("inverse")

                                if not (src and rel and tgt) or not self._is_valid_triplet(src, rel, tgt):
                                    continue

                                with ltm_engine._lock:
                                    if ltm_engine.graph.has_edge(src, tgt):
                                        existing_rel = ltm_engine.graph.edges[src, tgt].get('relation')
                                        if existing_rel == 'HAS_RELATION' and rel != 'HAS_RELATION':
                                            ltm_engine.graph.remove_edge(src, tgt)
                                    ltm_engine.record_triplet(src, rel, tgt, metadata=metadata, inverse=inverse)
                                    logger.info(f"LTM Final DB Entry: [{src}] --({rel})--> [{tgt}]")
                        except Exception as e:
                            logger.error(f"LTM Engine Save Error: {e}")
                break
            except Exception as e:
                logger.error(f"LTM API parsing/request error: {e}")
                time.sleep(1)

    def _start_background_pruning(self):
        try:
            threading.Thread(target=self._prune_old_messages, daemon=True).start()
            timer = threading.Timer(86400, self._start_background_pruning)
            timer.daemon = True
            timer.start()
        except Exception as e:
            logger.error(f"Pruning timer error: {e}")

    def _prune_old_messages(self):
        if not self.master_history:
            return
        try:
            now = datetime.now()
            raw_cutoff = now - timedelta(days=MEMORY_RAW_RETENTION_DAYS)
            summary_cutoff = now - timedelta(days=MEMORY_SUMMARY_RETENTION_DAYS)

            day_groups = {}
            for msg in self.master_history:
                try:
                    ts = datetime.fromisoformat(msg.get('timestamp', now.isoformat()))
                    if ts < raw_cutoff:
                        day_key = ts.strftime("%Y-%m-%d")
                        day_groups.setdefault(day_key, []).append(msg)
                except Exception:
                    continue

            for day_key, msgs in day_groups.items():
                if day_key not in self.daily_summaries and len(msgs) >= MEMORY_SUMMARY_MIN_MESSAGES:
                    self._generate_daily_summary(day_key, msgs)

            filtered_history = []
            for msg in self.master_history:
                try:
                    msg_time = datetime.fromisoformat(msg.get('timestamp', now.isoformat()))
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
            if any(w in msg_lower for w in ["code", "python", "error", "bug"]):
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
                "timestamp": now.isoformat()
            }
            if metadata:
                new_entry["metadata"] = metadata

            with self._lock:
                self.master_history.append(new_entry)

            self._append_history_jsonl(self.master_history_file, new_entry)

            if self.last_message_date != today_key:
                old_date = self.last_message_date
                self.last_message_date = today_key
                if old_date and old_date in self.daily_summaries:
                    pass
                else:
                    threading.Thread(
                        target=self._generate_daily_summary,
                        args=(old_date,),
                        daemon=True
                    ).start()

            ignore_words = ["ok", "okay", "yes", "no", "thanks", "thank you", "clear", "done", "nice", "cool", "hmm", "acha"]
            if role == "USER" and message.lower().strip() not in ignore_words:
                self._track_session_state(message)
                self._async_extract_permanent_facts(message)
        except Exception as e:
            logger.error(f"Error adding message to memory: {e}")

    def _format_entry(self, entry, dt):
        time_str = dt.strftime('%d %b, %H:%M')
        role = entry.get('role', 'UNKNOWN')
        message = entry.get('message', '')
        metadata = entry.get('metadata', {})

        if role == "CONVERSATION":
            block = f"[{time_str}]\n{message}"
        else:
            block = f"[{time_str}]\n<{role.capitalize()}>\n{message}"

        if metadata:
            log_content = []
            apps_opened = metadata.get("apps_opened", [])
            apps_closed = metadata.get("apps_closed", [])
            system_events = metadata.get("system_events", [])
            if apps_opened or apps_closed or system_events:
                log_content.append("  ACTIONS TAKEN:")
                if apps_opened:
                    log_content.append(f"  - Opened Apps: {', '.join(apps_opened)}")
                if apps_closed:
                    log_content.append(f"  - Closed Apps: {', '.join(apps_closed)}")
                for evt in system_events:
                    log_content.append(f"  - System: {evt}")
            if log_content:
                xml_log = "\n<System_Execution_Log>\n" + "\n".join(log_content).strip() + "\n</System_Execution_Log>"
                block += xml_log

        if role != "CONVERSATION":
            block += f"\n</{role.capitalize()}>"
        return block

    def get_fast_history_context(self):
        if not self.master_history:
            return "No recent conversation."
        try:
            history_str = []
            for entry in self.master_history[-10:]:
                time_str = datetime.fromisoformat(entry.get('timestamp', datetime.now().isoformat())).strftime('%H:%M')
                if entry.get('role') == "CONVERSATION":
                    history_str.append(f"[{time_str}] {entry.get('message', '')}")
                else:
                    history_str.append(f"[{time_str}] {entry.get('role', 'UNKNOWN')}: {entry.get('message', '')}")
            return "\n".join(history_str)
        except Exception as e:
            logger.error(f"Context retrieval error: {e}")
            return "Error retrieving history."

    def get_agentic_fast_context(self):
        if not self.master_history:
            return "<Recent_Context>\nNo recent conversation.\n</Recent_Context>"
        try:
            history_lines = ["<Recent_Context>"]
            for entry in self.master_history[-10:]:
                dt = datetime.fromisoformat(entry.get('timestamp', datetime.now().isoformat()))
                time_str = dt.strftime('%H:%M')
                role = entry.get('role', 'UNKNOWN')
                message = entry.get('message', '')
                metadata = entry.get('metadata', {})
                if role == "CONVERSATION":
                    block = f"[{time_str}]\n{message}"
                else:
                    block = f"[{time_str}]\n<{role.capitalize()}>\n{message}"
                if metadata:
                    log_content = []
                    apps_opened = metadata.get("apps_opened", [])
                    apps_closed = metadata.get("apps_closed", [])
                    system_events = metadata.get("system_events", [])
                    if apps_opened or apps_closed or system_events:
                        log_content.append("  ACTIONS TAKEN:")
                        if apps_opened:
                            log_content.append(f"  - Opened Apps: {', '.join(apps_opened)}")
                        if apps_closed:
                            log_content.append(f"  - Closed Apps: {', '.join(apps_closed)}")
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

    def get_relevant_context(self, query):
        try:
            context = [
                f"Current Time: {datetime.now().strftime('%A, %Y-%m-%d %H:%M')}",
                f"SESSION MODE: {self.current_mode}"
            ]
            return "\n".join(context)
        except Exception as e:
            logger.error(f"Relevant context retrieval error: {e}")
            return "Error retrieving relevant context."

    def get_chat_history_for_tool(self, query=None):
        try:
            today = datetime.now().date()
            raw_cutoff = today - timedelta(days=MEMORY_RAW_RETENTION_DAYS)
            raw_cutoff_str = raw_cutoff.strftime("%Y-%m-%d")

            query_terms = []
            if query and isinstance(query, str):
                query_terms = [t for t in re.findall(r'\w+', query.lower()) if len(t) > 2]

            def matches(text):
                if not query_terms:
                    return True
                text_lower = str(text).lower()
                return any(term in text_lower for term in query_terms)

            recent_blocks = []
            for entry in self.master_history:
                try:
                    ts = datetime.fromisoformat(entry.get('timestamp', ''))
                    date_key = ts.strftime("%Y-%m-%d")
                    if date_key >= raw_cutoff_str:
                        message = entry.get('message', '')
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
                    + "\n".join(summary_blocks)
                )
            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"History for tool retrieval error: {e}")
            return "Error retrieving conversation history."