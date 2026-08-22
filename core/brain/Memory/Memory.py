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
)


class ContextMemory:
    def __init__(self, memory_path="Data/jarvis_memory"):
        self.memory_path = Path(memory_path)
        self.memory_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.master_history_file = self.memory_path / "master_chat_history.jsonl"
        old_json_file = self.memory_path / "master_chat_history.json"

        if old_json_file.exists() and not self.master_history_file.exists():
            old_data = self._load_json(old_json_file, [])
            self._rewrite_history_jsonl(self.master_history_file, old_data)
            try:
                os.remove(old_json_file)
            except Exception as e:
                logger.error(f"Failed to remove old json file: {e}")

        self.master_history = self._load_history_jsonl(self.master_history_file)
        self.ephemeral = {}
        self.live_feedback_queue = []
        self.current_mode = "General Assistant"
        self.mode_timer = datetime.now()
        self._confirmation_timer = None

        try:
            self.ltm_client = openai.OpenAI(
                api_key=LTM_EXTRACTION_API_KEY,
                base_url=LTM_EXTRACTION_ENDPOINT,
            ) if LTM_EXTRACTION_API_KEY else None
        except Exception as e:
            logger.error(f"Failed to initialize LTM extraction client: {e}")
            self.ltm_client = None

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

    def _save_json(self, file_path, data):
        with self._lock:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save JSON to {file_path}: {e}")

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

    def _track_session_state(self, message):
        try:
            msg_lower = message.lower()
            if any(w in msg_lower for w in ["code", "python", "error", "bug"]):
                self.current_mode = "Technical"
            elif any(w in msg_lower for w in ["joke", "song", "play", "movie"]):
                self.current_mode = "Casual"
            self.mode_timer = datetime.now()
            if (datetime.now() - self.mode_timer).total_seconds() / 60 > 30:
                self.current_mode = "General Assistant"
        except Exception as e:
            logger.error(f"Session state error: {e}")

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
        try:
            from core.brain.Memory.LifetimeMemory import ltm_engine
            top_nodes = ltm_engine.get_all_node_names(limit=100)
            if top_nodes:
                existing_nodes_str = ", ".join(top_nodes)
        except Exception as e:
            logger.error(f"Failed to fetch LTM nodes: {e}")

        prompt = f"""You are the core LTM (Lifetime Memory) Engine for Jarvis.
Your job is to analyze the user's latest message using the context of the recent conversation, and extract ONLY permanent, long-lasting factual knowledge into a Graph structure.

[CRITICAL GUARDRAILS]:
1. ZERO-HALLUCINATION: If the message does not contain a CLEAR, UNDENIABLE permanent fact, you MUST return "is_permanent_fact": false. Do not guess, infer, or force a relation.
2. THE 1-YEAR TEST: Will this fact likely still be true or relevant 1 years from now? If 'No' (e.g., current mood, current task, upcoming trip), IGNORE it entirely and return false.

[WHAT TO IGNORE]:
- Commands & Actions ("open google", "send mail", "remind me").
- Temporary states ("I am eating pizza", "I am tired", "going to Delhi today").
- Chit-chat or greetings ("hello", "how are you", "ok", "thanks").
- Meta-instructions ("remember this", "note this down", "store this").

[WHAT TO SAVE]:
- Identity & Traits (Profession, Age, Habits, Skills).
- Relationships (Friends, Family, Colleagues).
- Hard Preferences (Likes, Dislikes, Allergies, Favorite things).
- Assets (Car owned, Phone model, Pets).

[ALLOWED RELATIONS]:
FAMILY: FATHER, MOTHER, BROTHER, SISTER, SON, DAUGHTER, SPOUSE, UNCLE, AUNT
PROFESSIONAL: WORKS_AS, EMPLOYED_AT, MANAGER_OF, COLLEAGUE
PERSONAL: FRIEND, NEIGHBOR, ROOMMATE, PARTNER
CORE: IS_A, LIKES, DISLIKES, OWNS, USES, PREFERS, HAS_SKILL, LOCATED_IN, CREATED

[EXTRACTION RULES]:
1. SPECIFICITY: Use the MOST SPECIFIC relation possible (e.g., FATHER instead of HAS_RELATION).
2. NO GENERICS: Never store generic facts like "User IS_A Person". Skip such entries.
3. PRONOUN RESOLUTION: Resolve pronouns (he/she/it) using the Context History. Replace pronouns with the actual entity names.
4. ENTITY NORMALIZATION: Keep entities short (1-3 words max) and in Title Case. Strip all articles (A, An, The). For example, "The Red Car" MUST become "Red Car".
5. NODE REUSE: Check EXISTING GRAPH NODES below. If the concept exists, use the EXACT matching node name.
6. FAMILY VALIDATION: If the relation is family-related, ensure both source and target are humans.
7. CONFLICT RESOLUTION: If a new fact contradicts an existing node in the graph, extract the NEW fact and explicitly explain the override in your reasoning.

[EXISTING GRAPH NODES]:
{existing_nodes_str}

[Context History]:
{recent_history if recent_history else 'No recent history.'}

[User's Latest Message]: "{message}"

Return STRICT JSON exactly in this schema:
{{
    "reasoning": "Explain why this passes the 5-Year Test, or why it fails/overrides.",
    "is_permanent_fact": boolean,
    "triplets": [
        {{
            "source": "Entity1",
            "relation": "ALLOWED_RELATION",
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
                        {"role": "system", "content": "You are a precise knowledge graph extraction engine. Output strictly valid JSON."},
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
                                    logger.info(f"LTM Saved: [{src}] --({rel})--> [{tgt}]")
                        except Exception as e:
                            logger.error(f"LTM Engine Save Error: {e}")
                break
            except Exception as e:
                logger.error(f"LTM API parsing/request error: {e}")
                time.sleep(1)

    def _start_background_pruning(self):
        try:
            self._prune_old_messages()
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
            fifteen_days_ago = now - timedelta(days=15)
            filtered_history = []
            for msg in self.master_history:
                try:
                    msg_time = datetime.fromisoformat(msg.get('timestamp', now.isoformat()))
                    if msg_time >= fifteen_days_ago:
                        filtered_history.append(msg)
                except Exception as e:
                    logger.error(f"Timestamp parse error: {e}")
            if len(filtered_history) < len(self.master_history):
                self.master_history = filtered_history
                self._rewrite_history_jsonl(self.master_history_file, self.master_history)
        except Exception as e:
            logger.error(f"Pruning history error: {e}")

    def add_message(self, role, message, metadata=None):
        if not message or not message.strip():
            return
        try:
            if metadata and isinstance(metadata, dict):
                for key, value in metadata.items():
                    if isinstance(value, str) and len(value) > 2000:
                        metadata[key] = value[:2000] + "\n\n[...Data Truncated to save Memory]"
            new_entry = {
                "role": role,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            if metadata:
                new_entry["metadata"] = metadata
            self.master_history.append(new_entry)
            self._append_history_jsonl(self.master_history_file, new_entry)
            ignore_words = ["ok", "okay", "yes", "no", "thanks", "thank you", "clear", "done", "nice", "cool", "hmm", "acha"]
            if role == "USER" and message.lower().strip() not in ignore_words:
                self._track_session_state(message)
                self._async_extract_permanent_facts(message)
        except Exception as e:
            logger.error(f"Error adding message to memory: {e}")

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

    def get_chat_history_for_tool(self):
        if not self.master_history:
            return "No conversation history found."
        try:
            history_lines = []
            for entry in self.master_history:
                dt = datetime.fromisoformat(entry.get('timestamp', datetime.now().isoformat()))
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
                        log_content.append("")
                    if log_content:
                        xml_log = "\n\n<System_Execution_Log>\n" + "\n".join(log_content).strip() + "\n</System_Execution_Log>"
                        block += xml_log
                if role != "CONVERSATION":
                    block += f"\n</{role.capitalize()}>"
                history_lines.append(block)
            return "\n\n".join(history_lines)
        except Exception as e:
            logger.error(f"History for tool retrieval error: {e}")
            return "Error retrieving conversation history."