import json
import os
import threading
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from groq import Groq
from core.logger.logger import logger
from core.brain.config import GROQ_SUMMARY_MODEL

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
            except Exception:
                pass

        self.master_history = self._load_history_jsonl(self.master_history_file)
        self.ephemeral = {}
        self.live_feedback_queue = []
        self.current_mode = "General Assistant"
        self.mode_timer = datetime.now()
        self._confirmation_timer = None

        try:
            self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        except Exception:
            self.groq_client = None

        self._start_background_pruning()

    def _is_valid_triplet(self, src, rel, tgt):
        invalid_entities = {"agent", "info", "system", "jarvis", "data", "unknown", "yes", "no", "today", "tomorrow", "now"}
        if src.lower() in invalid_entities or tgt.lower() in invalid_entities:
            return False
        
        if len(src) < 2 or len(tgt) < 2:
            return False
            
        if src.lower() == tgt.lower():
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
                except Exception:
                    pass
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
                except Exception:
                    pass
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
        except Exception:
            return default

    def _save_json(self, file_path, data):
        with self._lock:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    def _load_history_jsonl(self, file_path):
        history = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            history.append(json.loads(line))
            except Exception:
                pass
        return history

    def _append_history_jsonl(self, file_path, entry):
        with self._lock:
            try:
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def _rewrite_history_jsonl(self, file_path, data_list):
        with self._lock:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for entry in data_list:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

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
        except Exception:
            pass

    def _async_extract_permanent_facts(self, message):
        try:
            thread = threading.Thread(target=self._extract_permanent_facts_ai, args=(message,))
            thread.daemon = True
            thread.start()
        except Exception:
            pass

    def _extract_permanent_facts_ai(self, message):
        if not self.groq_client or len(message.split()) < 2:
            return
        
        recent_history = ""
        if self.master_history:
            recent_history = "\n".join([f"{msg.get('role', '')}: {msg.get('message', '')}" for msg in self.master_history[-6:]])
        
        existing_nodes_str = "None"
        try:
            from core.brain.Memory.LifetimeMemory import ltm_engine
            top_nodes = ltm_engine.get_all_node_names(limit=100)
            if top_nodes:
                existing_nodes_str = ", ".join(top_nodes)
        except Exception:
            pass

        prompt = f"""You are the core LTM Engine for Jarvis.
Your job is to analyze the user's latest message with the context of the recent conversation, and extract ONLY permanent, long-lasting factual knowledge into a Graph structure (Triplets).

[WHAT TO IGNORE]:
- Commands & Actions ("open google", "send mail", "remind me").
- Temporary states ("I am eating pizza", "I am tired", "going to Delhi").
- Chit-chat or greetings ("hello", "how are you", "ok", "thanks").
- Meta-instructions ("remember this", "note this down", "store this").

[WHAT TO SAVE]:
- Identity & Traits (Profession, Age, Habits, Skills).
- Relationships (Friends, Family, Colleagues).
- Hard Preferences (Likes, Dislikes, Allergies, Favorite things).
- Assets (Car owned, Phone model, Pets).

[ALLOWED RELATIONS]:
You MUST strictly use one of these uppercase relations:
[IS_A, LIKES, DISLIKES, OWNS, HAS_SKILL, WORKS_AS, HAS_RELATION, LOCATED_IN, USES, CREATED, PREFERS]

[RULES]:
1. If the user says "my friend Rahul", Source="User", Relation="HAS_RELATION", Target="Rahul".
2. Resolve pronouns (he/she/it) using the Context History.
3. Keep entities short (1-3 words max).
4. Check EXISTING GRAPH NODES below. If the concept exists, use the EXACT matching node name.

[EXISTING GRAPH NODES]:
{existing_nodes_str}

[Context History]:
{recent_history if recent_history else "No recent history."}

[User's Latest Message]: "{message}"

Return STRICT JSON exactly in this schema:
{{
    "reasoning": "string",
    "is_permanent_fact": boolean,
    "triplets": [
        {{"source": "Entity1", "relation": "ALLOWED_RELATION", "target": "Entity2"}}
    ]
}}
"""
        for _ in range(3):
            try:
                response = self.groq_client.chat.completions.create(
                    model=GROQ_SUMMARY_MODEL,
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
                                
                                if src and rel and tgt and self._is_valid_triplet(src, rel, tgt):
                                    ltm_engine.record_triplet(src, rel, tgt)
                                    logger.info(f"LTM Saved: [{src}] --({rel})--> [{tgt}]")
                        except Exception as e:
                            logger.error(f"LTM Engine Save Error: {e}")
                break
            except Exception:
                time.sleep(1)

    def _start_background_pruning(self):
        try:
            self._prune_old_messages()
            timer = threading.Timer(86400, self._start_background_pruning)
            timer.daemon = True
            timer.start()
        except Exception:
            pass

    def _prune_old_messages(self):
        if not self.master_history:
            return
        try:
            now = datetime.now()
            fifteen_days_ago = now - timedelta(days=15)
            filtered_history = []
            messages_to_archive = []
            for msg in self.master_history:
                try:
                    msg_time = datetime.fromisoformat(msg.get('timestamp', now.isoformat()))
                    if msg_time >= fifteen_days_ago:
                        filtered_history.append(msg)
                    else:
                        messages_to_archive.append(msg)
                except Exception:
                    pass
            if messages_to_archive:
                try:
                    from core.brain.Memory.LifetimeMemory import ltm_engine
                    ltm_engine.archive_old_chats(messages_to_archive)
                except Exception:
                    pass
            if len(filtered_history) < len(self.master_history):
                self.master_history = filtered_history
                self._rewrite_history_jsonl(self.master_history_file, self.master_history)
        except Exception:
            pass

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
        except Exception:
            pass

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
        except Exception:
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
        except Exception:
            return "<Recent_Context>\nError retrieving history.\n</Recent_Context>"

    def get_relevant_context(self, query):
        try:
            context = [
                f"Current Time: {datetime.now().strftime('%A, %Y-%m-%d %H:%M')}",
                f"SESSION MODE: {self.current_mode}"
            ]
            return "\n".join(context)
        except Exception:
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
        except Exception:
            return "Error retrieving conversation history."