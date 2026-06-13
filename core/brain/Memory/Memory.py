import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from groq import Groq
from core.logger.logger import logger
from tools.workspace.workspace import workspace

from core.brain.config import GROQ_SUMMARY_MODEL

class ContextMemory:
    def __init__(self, memory_path="Data/jarvis_memory"):
        self.memory_path = Path(memory_path)
        self.memory_path.mkdir(parents=True, exist_ok=True)
        
        self._lock = threading.Lock()
        
        self.user_bio_file = self.memory_path / "user_bio.json" 
        self.preferences_file = self.memory_path / "preferences.json"
        self.user_mood_file = self.memory_path / "user_mood.json"
        
        self.master_history_file = self.memory_path / "master_chat_history.json"
        
        self.user_bio = self._load_json(self.user_bio_file, {"name": "User", "facts": []})
        self.preferences = self._load_json(self.preferences_file, {"likes": []})
        self.user_mood = self._load_json(self.user_mood_file, {"mood_history": []})
        
        self.master_history = self._load_json(self.master_history_file, [])

        self.ephemeral = {} 
        
        self.live_feedback_queue = []
        
        self.current_mode = "General Assistant"
        self.mode_timer = datetime.now()
        
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        logger.info("🧠 15-Day Linear Memory System Initialized (Gemma-Ready + Action Tracking)")

    def add_live_feedback(self, text):
        """Adds a live instruction to the queue while agent is running."""
        if text and text.strip():
            self.live_feedback_queue.append(text.strip())
            logger.info(f"⚡ Live feedback added to memory queue: {text}")

    def get_and_clear_feedback(self):
        """Fetches all pending feedback and clears the queue."""
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
            return default
    
    def _save_json(self, file_path, data):
        with self._lock:
            try:
                with open(file_path, 'w', encoding='utf-8') as f: 
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e: 
                logger.error(f"Failed to save {file_path.name}: {e}")

    def _track_session_state(self, message):
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["code", "python", "error", "bug"]): self.current_mode = "Technical"
        elif any(w in msg_lower for w in ["joke", "song", "play", "movie"]): self.current_mode = "Casual"
        self.mode_timer = datetime.now()
        if (datetime.now() - self.mode_timer).total_seconds() / 60 > 30: self.current_mode = "General Assistant"

    def _async_extract_insights(self, message):
        thread = threading.Thread(target=self._extract_insights_ai, args=(message,))
        thread.daemon = True
        thread.start()

    def _extract_insights_ai(self, message):
        if len(message.split()) < 3: return 
            
        recent_history = ""
        if self.master_history:
            recent_history = "\n".join([f"{msg['role']}: {msg['message']}" for msg in self.master_history[-4:]])

        try:
            prompt = f"""Analyze the user's latest message to extract ONLY NEW, high-value personal insights AND their current emotional state.

            🚨 STRICT FILTERS & RULES:
            1. The 30-Day Rule: Will this info (bio/prefs) be useful to know a month from now? If no, DO NOT save it.
            2. The Assistant Rule: Only save things that an AI Assistant needs to know (workflow, major life facts, relationships).
            3. No Duplicates / Update Rule: Review the [EXISTING KNOWLEDGE] block. DO NOT extract facts we already know. Only extract if it's new or a modification to existing info.
            4. Mood Tracker: ALWAYS detect the current emotional 'mood' (e.g., Happy, Tired, Stressed, Excited, Frustrated, Neutral) based on the tone of the user's message and the recent conversation history.

            [EXISTING KNOWLEDGE]
            Known Bio Facts: {[f['text'] for f in self.user_bio.get("facts", [])]}
            Known Preferences: {self.preferences.get("likes", [])}

            [RECENT CONVERSATION HISTORY]
            {recent_history if recent_history else "No recent history."}

            CATEGORIES:
            1. 'bio': Hard, unchanging facts (Name, Profession, City, Goals).
            2. 'prefs': Actionable preferences (Coding style, habits).
            3. 'mood': A single word describing the user's current emotional vibe.

            Return STRICTLY a JSON object. Format: {{"bio": ["new fact 1"], "prefs": ["new pref 1"], "mood": "Tired"}}
            If no NEW bio/prefs meet the filters, return empty arrays but ALWAYS return a mood: {{"bio": [], "prefs": [], "mood": "Neutral"}}
            
            User's Latest Message: "{message}"
            """
            
            response = self.groq_client.chat.completions.create(
                model=GROQ_SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": "You are a highly analytical memory and sentiment extractor. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            raw_text = response.choices[0].message.content.strip()
            import re
            clean_text = re.sub(r'^```json\n|```$', '', raw_text, flags=re.MULTILINE).strip()
            insights = json.loads(clean_text)
            
            updated = False
            mood_updated = False
            
            if insights.get("bio") and len(insights["bio"]) > 0:
                for fact in insights["bio"]:
                    if not any(f["text"].lower() == fact.lower() for f in self.user_bio["facts"]):
                        self.user_bio["facts"].append({"text": fact, "date": datetime.now().isoformat()})
                        updated = True
                if updated: self._save_json(self.user_bio_file, self.user_bio)
            
            if insights.get("prefs") and len(insights["prefs"]) > 0:
                for pref in insights["prefs"]:
                    if not any(p.lower() == pref.lower() for p in self.preferences["likes"]):
                        self.preferences["likes"].append(pref)
                        updated = True
                if len(self.preferences["likes"]) > 20: self.preferences["likes"] = self.preferences["likes"][-20:]
                if updated: self._save_json(self.preferences_file, self.preferences)
                
            current_mood = insights.get("mood", "Neutral")
            if current_mood and current_mood.lower() != "neutral":
                now = datetime.now()
                mood_entry = {
                    "mood": current_mood.capitalize(),
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M")
                }
                self.user_mood["mood_history"].append(mood_entry)
                if len(self.user_mood["mood_history"]) > 10:
                    self.user_mood["mood_history"] = self.user_mood["mood_history"][-10:]
                self._save_json(self.user_mood_file, self.user_mood)
                mood_updated = True
                
            if updated or mood_updated: 
                logger.info(f"🧠 AI learned NEW context/mood: {insights}")
                    
        except Exception as e:
            logger.error(f"AI Insights extraction failed: {e}")

    def _prune_old_messages(self):
        """Removes messages older than 15 days from the master history and archives them to LTM."""
        now = datetime.now()
        fifteen_days_ago = now - timedelta(days=15)
        
        filtered_history = []
        messages_to_archive = []
        
        for msg in self.master_history:
            try:
                msg_time = datetime.fromisoformat(msg['timestamp'])
                if msg_time >= fifteen_days_ago:
                    filtered_history.append(msg)
                else:
                    messages_to_archive.append(msg)
            except Exception:
                pass 
                
        if messages_to_archive:
            try:
                from core.brain.Memory.LifetimeMemory import ltm_engine
                logger.info(f"📦 Found {len(messages_to_archive)} old messages. Sending to Lifetime Memory for summarization...")
                ltm_engine.archive_old_chats(messages_to_archive)
            except Exception as e:
                logger.error(f"⚠️ Failed to trigger LTM archive: {e}")
                
        if len(filtered_history) < len(self.master_history):
            self.master_history = filtered_history
            logger.info("🧹 Cleaned up and archived messages older than 15 days.")

    def add_message(self, role, message, metadata=None):
        if not message or not message.strip(): return
        
        new_entry = {
            "role": role, 
            "message": message, 
            "timestamp": datetime.now().isoformat()
        }
        
        if metadata:
            new_entry["metadata"] = metadata

        self.master_history.append(new_entry)
        self._prune_old_messages()
        self._save_json(self.master_history_file, self.master_history)

        ignore_words = ["ok", "okay", "yes", "no", "thanks", "thank you", "clear", "done", "nice", "cool", "hmm", "acha"]
        
        if role == "USER" and message.lower().strip() not in ignore_words:
            self._track_session_state(message)
            self._async_extract_insights(message)

    def get_fast_history_context(self):
        """Returns ONLY the last 10 messages for the Groq Fast Brain to save TPM."""
        if not self.master_history: return "No recent conversation."
        
        history_str = []
        for entry in self.master_history[-10:]:
            time_str = datetime.fromisoformat(entry['timestamp']).strftime('%H:%M')
            if entry['role'] == "CONVERSATION":
                history_str.append(f"[{time_str}] {entry['message']}")
            else:
                history_str.append(f"[{time_str}] {entry['role']}: {entry['message']}")
                
        return "\n".join(history_str)

    def get_agentic_fast_context(self):
        """Returns ONLY the last 10 messages with strict XML and execution logs for Agentic context."""
        if not self.master_history: 
            return "<Recent_Context>\nNo recent conversation.\n</Recent_Context>"
        
        history_lines = ["<Recent_Context>"]
        for entry in self.master_history[-10:]:
            dt = datetime.fromisoformat(entry['timestamp'])
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
                files_touched = metadata.get("files_touched", [])
                
                if apps_opened or apps_closed or system_events:
                    log_content.append("  🛠️ ACTIONS TAKEN:")
                    if apps_opened: log_content.append(f"  - Opened Apps: {', '.join(apps_opened)}")
                    if apps_closed: log_content.append(f"  - Closed Apps: {', '.join(apps_closed)}")
                    for evt in system_events: log_content.append(f"  - System: {evt}")
                    log_content.append("")
                    
                if files_touched:
                    log_content.append("  📂 WORKSPACE ACTIVITY:")
                    for f in files_touched:
                        log_content.append(f"  - Action: {f.get('action_type', 'Touched')} file '{f.get('file_name', 'unknown')}'")
                
                if log_content:
                    xml_log = "\n<System_Execution_Log>\n" + "\n".join(log_content).strip() + "\n</System_Execution_Log>"
                    block += xml_log
            
            if role != "CONVERSATION":
                block += f"\n</{role.capitalize()}>"
                
            history_lines.append(block)
            
        history_lines.append("</Recent_Context>")
        return "\n\n".join(history_lines)

    def get_relevant_context(self, query):
        """Returns ONLY Bio, Prefs, and Workspace status (Lightweight Initial Context)."""
        context = [
            f"⏱️ Current Time: {datetime.now().strftime('%A, %Y-%m-%d %H:%M')}",
            f"🧠 SESSION MODE: {self.current_mode}"
        ]
        
        if self.user_bio.get("facts"):
            context.append("\n👤 USER FACTS:\n" + "\n".join([f"- {fact['text']}" for fact in self.user_bio["facts"]]))
        if self.preferences.get("likes"):
            context.append("\n🎯 USER PREFS:\n" + "\n".join([f"- {like}" for like in self.preferences["likes"]]))
        
        if self.user_mood.get("mood_history"):
            moods = "\n".join([f"- {m['date']} {m['time']} | Mood: {m['mood']}" for m in self.user_mood["mood_history"][-5:]])
            context.append(f"\n🎭 RECENT MOOD HISTORY:\n{moods}")
            
        workspace_data = workspace.get_workspace_context()
        context.append(f"\n📁 MY WORKSPACE FILES & STORAGE STATUS:\n{workspace_data}")
                
        return "\n".join(context)

    def get_chat_history_for_tool(self):
        """Returns the full 15-day raw chat history log, styled with XML tags for LLMs."""
        if not self.master_history:
            return "No conversation history found."
            
        history_lines = []
        for entry in self.master_history:
            dt = datetime.fromisoformat(entry['timestamp'])
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
                files_touched = metadata.get("files_touched", [])
                
                if apps_opened or apps_closed or system_events:
                    log_content.append("  🛠️ ACTIONS TAKEN:")
                    if apps_opened: log_content.append(f"  - Opened Apps: {', '.join(apps_opened)}")
                    if apps_closed: log_content.append(f"  - Closed Apps: {', '.join(apps_closed)}")
                    for evt in system_events: log_content.append(f"  - System: {evt}")
                    log_content.append("")
                    
                if files_touched:
                    log_content.append("  📂 WORKSPACE ACTIVITY:")
                    for f in files_touched:
                        log_content.append(f"  - Action: {f.get('action_type', 'Touched')} file '{f.get('file_name', 'unknown')}'")
                        content = f.get('content', '')
                        if content:
                            log_content.append(f"  - Content Snippet:\n    ```\n    {content}\n    ```")
                
                if log_content:
                    xml_log = "\n\n<System_Execution_Log>\n" + "\n".join(log_content).strip() + "\n</System_Execution_Log>"
                    block += xml_log
            
            if role != "CONVERSATION":
                block += f"\n</{role.capitalize()}>"
                
            history_lines.append(block)
                
        return "\n\n".join(history_lines)