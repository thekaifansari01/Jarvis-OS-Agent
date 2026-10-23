import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from scipy.spatial.distance import cosine

from core.logger.logger import logger

VALID_BEHAVIORAL_DOMAINS = {"coding", "scheduling", "communication", "ui_design", "lifestyle"}

EXPLICIT_PERMANENT_REGEX = re.compile(
    r"\b(hamesha|always|never|kabhi\s*nahi|kabhi\s*mat|yaad\s*rakhna|remember\s*that|"
    r"from\s*now\s*on|aage\s*se|roz|rozana|daily|every\s*day|every\s*morning|"
    r"every\s*night|aadat|routine|usually|aksar|meri\s*aadat)\b",
    re.IGNORECASE,
)

OPPOSITION_GROUPS = [
    ({"dark", "black", "amoled"}, {"light", "white", "bright"}),
    ({"short", "concise", "brief", "compact", "minimal"}, {"long", "detailed", "verbose", "elaborate", "comprehensive"}),
    ({"morning", "subah", "early", "dawn"}, {"night", "raat", "late", "midnight", "evening", "shaam"}),
    ({"formal", "professional", "polite"}, {"casual", "informal", "friendly", "chill", "frank"}),
    ({"modular", "split", "multi-file", "separate"}, {"monolithic", "single-file", "one-file", "inline"}),
]

NEGATION_TOKENS = {
    "no", "not", "never", "without", "avoid", "dislike", "hate",
    "dont", "don't", "mat", "nahi", "na", "skip", "omit", "remove", "disable"
}

AFFIRMATIVE_TOKENS = {
    "always", "prefer", "like", "love", "include", "add", "use",
    "with", "keep", "enable", "hamesha", "pasand", "chahiye", "want"
}

STOPWORDS = {
    "user", "prefers", "likes", "wants", "always", "never", "when", "while",
    "the", "and", "for", "with", "without", "that", "this", "from", "into",
    "should", "must", "applicable", "requests", "asking", "tasks", "general"
}


class BehavioralPatternEngine:
    def __init__(self, memory_dir="Data/jarvis_memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.patterns_file = self.memory_dir / "behavioral_patterns.jsonl"
        self._lock = threading.RLock()

        self.dedupe_threshold = 0.82
        self.conflict_sim_threshold = 0.72
        self.similarity_threshold = 0.72
        self.min_confidence_gate = 0.85
        self.top_k = 2
        self.recency_decay_days = 180
        self.candidate_ttl_days = 30

        self._last_cache_key = None
        self._last_ephemeral_block = ""

        self.patterns = self._load_patterns()
        self._prune_stale_candidates()

        logger.info(
            f"BehavioralPatternEngine ready | patterns_loaded={len(self.patterns)} "
            f"| active={sum(1 for p in self.patterns if p.get('active', True))}"
        )

    @staticmethod
    def _normalize_topic(topic: str, meaning: str = "", domain: str = "") -> str:
        clean = re.sub(r"[^a-z0-9_]+", "_", (topic or "").strip().lower()).strip("_")
        if clean and len(clean) >= 3:
            return clean
        low = (meaning or "").lower()
        if any(w in low for w in ("dark mode", "light mode", "theme", "glassmorphism", "color", "palette")):
            return "ui_theme"
        if any(w in low for w in ("comment", "comments", "docstring")):
            return "code_comments"
        if any(w in low for w in ("short", "concise", "brief", "detailed", "length", "reply", "tone")):
            return "communication_style"
        if any(w in low for w in ("morning", "night", "subah", "raat", "schedule", "slot", "wake", "sleep")):
            return f"{domain or 'general'}_timing"
        return ""

    @staticmethod
    def _build_embed_text(pattern_entry: dict) -> str:
        meaning = (pattern_entry.get("meaning") or "").strip().rstrip(".")
        triggers = (pattern_entry.get("trigger_contexts") or "").strip().rstrip(".")
        topic = (pattern_entry.get("topic") or "").replace("_", " ").strip()
        raw = (pattern_entry.get("raw_statement") or "").strip()

        parts = []
        if triggers:
            parts.append(triggers)
        if meaning:
            parts.append(meaning)
        if topic:
            parts.append(f"Topic: {topic}")
        if not parts and raw:
            parts.append(raw)
        return ". ".join(parts)

    @staticmethod
    def _infer_domain_from_text(text: str) -> str:
        low = (text or "").lower()
        if any(w in low for w in ("schedule", "timetable", "study", "morning", "night", "8 pm", "hour", "slot", "routine", "wake", "sleep")):
            return "scheduling"
        if any(w in low for w in ("dark mode", "light mode", "glassmorphism", "ui", "css", "dashboard", "theme", "frontend", "layout", "design")):
            return "ui_design"
        if any(w in low for w in ("code", "coding", "python", "script", "comment", "modular", "ide", "react", "programming")):
            return "coding"
        if any(w in low for w in ("email", "mail", "whatsapp", "telegram", "message", "tone", "formal", "reply", "short")):
            return "communication"
        return "lifestyle"

    @staticmethod
    def _extract_content_tokens(text: str) -> set:
        tokens = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
        return {t for t in tokens if len(t) >= 3 and t not in STOPWORDS and t not in NEGATION_TOKENS and t not in AFFIRMATIVE_TOKENS}

    @classmethod
    def _is_contradictory(cls, old_entry: dict, new_entry: dict) -> bool:
        old_text = f"{old_entry.get('meaning', '')} {old_entry.get('raw_statement', '')}".lower()
        new_text = f"{new_entry.get('meaning', '')} {new_entry.get('raw_statement', '')}".lower()

        old_words = set(re.findall(r"[a-z0-9']+", old_text))
        new_words = set(re.findall(r"[a-z0-9']+", new_text))

        for side_a, side_b in OPPOSITION_GROUPS:
            if (old_words & side_a and new_words & side_b) or (old_words & side_b and new_words & side_a):
                return True

        old_type = str(old_entry.get("type", "preference")).lower()
        new_type = str(new_entry.get("type", "preference")).lower()
        old_neg = bool(old_words & NEGATION_TOKENS) or old_type == "dislike"
        new_neg = bool(new_words & NEGATION_TOKENS) or new_type == "dislike"

        if old_neg != new_neg:
            old_content = cls._extract_content_tokens(old_entry.get("meaning", ""))
            new_content = cls._extract_content_tokens(new_entry.get("meaning", ""))
            if old_content and new_content and (old_content & new_content):
                return True

        old_topic = old_entry.get("topic", "")
        new_topic = new_entry.get("topic", "")
        if old_topic and new_topic and old_topic == new_topic and old_neg != new_neg:
            return True

        return False

    def _invalidate_cache(self):
        with self._lock:
            self._last_cache_key = None
            self._last_ephemeral_block = ""

    def _prune_stale_candidates(self):
        with self._lock:
            if not self.patterns:
                return
            now = datetime.now()
            kept = []
            removed = 0
            for p in self.patterns:
                if p.get("active", True):
                    kept.append(p)
                    continue
                try:
                    last_dt = datetime.fromisoformat(p.get("last_mentioned", ""))
                    if (now - last_dt).days > self.candidate_ttl_days:
                        removed += 1
                        continue
                except Exception:
                    pass
                kept.append(p)
            if removed > 0:
                self.patterns = kept
                self._invalidate_cache()
                self._save_patterns()
                logger.info(f"BehavioralPatternEngine pruned {removed} expired candidate patterns.")

    def _load_patterns(self):
        if not self.patterns_file.exists():
            return []
        loaded = []
        try:
            with open(self.patterns_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if isinstance(entry, dict) and entry.get("raw_statement"):
                            entry.pop("_embedding", None)
                            if "domain" not in entry or entry["domain"] not in VALID_BEHAVIORAL_DOMAINS:
                                combined = f"{entry.get('meaning', '')} {entry.get('trigger_contexts', '')}"
                                entry["domain"] = self._infer_domain_from_text(combined)
                            entry["topic"] = self._normalize_topic(
                                entry.get("topic", ""),
                                entry.get("meaning", ""),
                                entry["domain"],
                            )
                            if "active" not in entry:
                                count = int(entry.get("evidence_count", 1))
                                conf = float(entry.get("confidence", 0.7))
                                raw_s = entry.get("raw_statement", "")
                                is_perm = bool(EXPLICIT_PERMANENT_REGEX.search(raw_s))
                                entry["active"] = bool(count >= 2 or is_perm or conf >= 0.85)
                            loaded.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"BehavioralPatternEngine load error: {e}")
            return []
        if loaded:
            self._refresh_embeddings(loaded)
        return loaded

    def _refresh_embeddings(self, patterns_list):
        if not patterns_list:
            return
        try:
            from core.brain.Memory.LifetimeMemory import ltm_engine
            texts = [self._build_embed_text(p) for p in patterns_list]
            embs = ltm_engine.embed(texts, is_query=False)
            if embs and len(embs) == len(patterns_list):
                for p, emb in zip(patterns_list, embs):
                    p["_embedding"] = emb
        except Exception as e:
            logger.error(f"BehavioralPatternEngine embed refresh error: {e}")

    def _save_patterns(self):
        with self._lock:
            try:
                tmp_path = self.patterns_file.with_suffix(".jsonl.tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    for p in self.patterns:
                        clean = {k: v for k, v in p.items() if not k.startswith("_")}
                        f.write(json.dumps(clean, ensure_ascii=False) + "\n")
                os.replace(tmp_path, self.patterns_file)
            except Exception as e:
                logger.error(f"BehavioralPatternEngine save error: {e}")

    def _upsert_pattern(self, new_pattern: dict):
        if not isinstance(new_pattern, dict):
            return
        raw = (new_pattern.get("raw_statement") or "").strip()
        meaning = (new_pattern.get("meaning") or "").strip()
        triggers = (new_pattern.get("trigger_contexts") or "").strip()
        conf = float(new_pattern.get("confidence", 0.0))

        if not raw or len(raw.split()) < 3 or not meaning:
            return

        if conf < self.min_confidence_gate:
            logger.debug(
                f"Behavioral pattern rejected by confidence gate ({conf:.2f} < {self.min_confidence_gate}): '{raw[:45]}'"
            )
            return

        domain = str(new_pattern.get("domain") or "").strip().lower()
        if domain not in VALID_BEHAVIORAL_DOMAINS:
            domain = self._infer_domain_from_text(f"{meaning} {triggers}")

        topic = self._normalize_topic(new_pattern.get("topic", ""), meaning, domain)
        new_pattern["domain"] = domain
        new_pattern["topic"] = topic

        is_explicit_perm = bool(
            new_pattern.get("is_explicit_permanent", False)
            or EXPLICIT_PERMANENT_REGEX.search(raw)
        )

        embed_text = self._build_embed_text({
            "raw_statement": raw,
            "meaning": meaning,
            "trigger_contexts": triggers,
            "topic": topic,
        })
        try:
            from core.brain.Memory.LifetimeMemory import ltm_engine
            new_emb = ltm_engine.embed(embed_text, is_query=False)
        except Exception as e:
            logger.warning(f"BehavioralPatternEngine embed new pattern error: {e}")
            return

        if new_emb is None:
            return

        with self._lock:
            best_idx = -1
            best_sim = 0.0
            topic_match_idx = -1

            for idx, ex in enumerate(self.patterns):
                if topic and ex.get("domain") == domain and ex.get("topic") == topic:
                    topic_match_idx = idx

                ex_emb = ex.get("_embedding")
                if not ex_emb:
                    continue
                try:
                    sim = 1.0 - float(cosine(new_emb, ex_emb))
                except Exception:
                    continue
                if sim > best_sim:
                    best_sim = sim
                    best_idx = idx

            now_iso = datetime.now().isoformat()

            target_idx = -1
            if topic_match_idx >= 0:
                target_idx = topic_match_idx
            elif best_idx >= 0 and best_sim >= self.dedupe_threshold:
                target_idx = best_idx
            elif (
                best_idx >= 0
                and best_sim >= self.conflict_sim_threshold
                and self.patterns[best_idx].get("domain") == domain
                and self._is_contradictory(self.patterns[best_idx], new_pattern)
            ):
                target_idx = best_idx

            if target_idx >= 0:
                ex = self.patterns[target_idx]
                if self._is_contradictory(ex, new_pattern):
                    ex["type"] = new_pattern.get("type", "preference")
                    ex["domain"] = domain
                    ex["topic"] = topic or ex.get("topic", "")
                    ex["raw_statement"] = raw
                    ex["meaning"] = meaning
                    if triggers:
                        ex["trigger_contexts"] = triggers
                    ex["confidence"] = round(max(conf, 0.88), 3)
                    ex["evidence_count"] = 1
                    ex["active"] = True
                    ex["first_mentioned"] = now_iso
                    ex["last_mentioned"] = now_iso
                    ex["_embedding"] = new_emb
                    logger.info(
                        f"Behavioral pattern SUPERSEDED contradictory preference [domain={domain} | topic={ex['topic']}]: '{meaning[:50]}'"
                    )
                else:
                    ex["evidence_count"] = int(ex.get("evidence_count", 1)) + 1
                    ex["last_mentioned"] = now_iso
                    old_conf = float(ex.get("confidence", 0.8))
                    ex["confidence"] = round(min(0.98, max(old_conf, conf) + 0.05), 3)
                    ex["active"] = True
                    ex["type"] = new_pattern.get("type", ex.get("type", "preference"))
                    ex["domain"] = domain
                    if topic:
                        ex["topic"] = topic
                    ex["raw_statement"] = raw
                    ex["meaning"] = meaning
                    if triggers:
                        ex["trigger_contexts"] = triggers
                    ex["_embedding"] = new_emb
                    logger.info(
                        f"Behavioral pattern reinforced & ACTIVE: '{meaning[:50]}' "
                        f"(sim={best_sim:.2f}, count={ex['evidence_count']}, conf={ex['confidence']})"
                    )
            else:
                is_active_immediately = bool(is_explicit_perm or conf >= 0.90)
                entry = {
                    "type": new_pattern.get("type", "preference"),
                    "domain": domain,
                    "topic": topic,
                    "raw_statement": raw,
                    "meaning": meaning,
                    "trigger_contexts": triggers,
                    "confidence": round(conf, 3),
                    "evidence_count": 1,
                    "active": is_active_immediately,
                    "first_mentioned": now_iso,
                    "last_mentioned": now_iso,
                    "_embedding": new_emb,
                }
                self.patterns.append(entry)
                state_label = "ACTIVE" if is_active_immediately else "CANDIDATE (awaiting 2nd confirmation)"
                logger.info(f"Behavioral pattern stored [{state_label} | domain={domain} | topic={topic}]: '{meaning[:50]}'")

            self._invalidate_cache()
            self._save_patterns()

    def get_relevant_patterns(
        self,
        query_text: str,
        mode: str = "agentic",
        english_query: str = "",
        domain: str = "",
    ):
        if not self.patterns:
            return []

        clean_domain = (domain or "").strip().lower()
        if clean_domain == "general_none":
            return []

        search_text = (english_query or query_text or "").strip()
        if not search_text:
            return []

        try:
            from core.brain.Memory.LifetimeMemory import ltm_engine
            query_emb = ltm_engine.embed(search_text, is_query=True)
        except Exception as e:
            logger.warning(f"BehavioralPatternEngine query embed error: {e}")
            return []

        if query_emb is None:
            return []

        now = datetime.now()
        scored = []

        with self._lock:
            for p in self.patterns:
                if not p.get("active", True):
                    continue

                p_domain = p.get("domain", "")
                if clean_domain in VALID_BEHAVIORAL_DOMAINS and p_domain in VALID_BEHAVIORAL_DOMAINS:
                    if p_domain != clean_domain:
                        compatible = (
                            {clean_domain, p_domain} == {"coding", "ui_design"}
                            or {clean_domain, p_domain} == {"scheduling", "lifestyle"}
                        )
                        if not compatible:
                            continue

                emb = p.get("_embedding")
                if not emb:
                    continue
                try:
                    sim = 1.0 - float(cosine(query_emb, emb))
                except Exception:
                    continue

                if clean_domain in VALID_BEHAVIORAL_DOMAINS and p_domain == clean_domain:
                    effective_threshold = self.similarity_threshold - 0.03
                else:
                    effective_threshold = self.similarity_threshold + 0.04

                if sim < effective_threshold:
                    continue

                conf = float(p.get("confidence", 0.85))
                score = sim * (0.7 + 0.3 * conf)

                try:
                    last_dt = datetime.fromisoformat(p.get("last_mentioned", ""))
                    days_old = max(0, (now - last_dt).days)
                    decay = max(0.6, 1.0 - (days_old / self.recency_decay_days) * 0.4)
                    score *= decay
                except Exception:
                    pass

                scored.append({
                    "pattern": p,
                    "score": round(score, 3),
                    "similarity": round(sim, 3),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        selected = []
        seen_topics = set()
        for item in scored:
            p_topic = item["pattern"].get("topic", "")
            if p_topic and p_topic in seen_topics:
                continue
            if p_topic:
                seen_topics.add(p_topic)
            selected.append(item)
            if len(selected) >= self.top_k:
                break
        return selected

    def format_ephemeral_block(
        self,
        current_command: str = "",
        mode: str = "agentic",
        recent_context: str = "",
        english_query: str = "",
        domain: str = "",
    ) -> str:
        query_text = (current_command or "").strip()
        if not query_text:
            return ""

        cache_key = f"{query_text}||{english_query}||{domain}||{mode}"
        with self._lock:
            if cache_key == self._last_cache_key:
                return self._last_ephemeral_block

        matches = self.get_relevant_patterns(
            query_text=query_text,
            mode=mode,
            english_query=english_query,
            domain=domain,
        )
        if not matches:
            with self._lock:
                self._last_cache_key = cache_key
                self._last_ephemeral_block = ""
            return ""

        lines = [
            "[BEHAVIORAL PATTERNS — VERIFIED USER PREFERENCES]",
            "Apply the following verified user preferences SILENTLY if they directly fit the current <Mission>:",
        ]

        for m in matches:
            p = m["pattern"]
            raw = p.get("raw_statement", "")
            meaning = p.get("meaning", "")
            p_dom = p.get("domain", "general")
            sim = m["similarity"]
            lines.append(
                f'- [{p_dom.upper()}] {meaning} (User previously stated: "{raw}" | Match: {sim:.2f})'
            )

        result_block = "\n".join(lines).rstrip()
        with self._lock:
            self._last_cache_key = cache_key
            self._last_ephemeral_block = result_block
        return result_block

    def get_all_patterns(self):
        with self._lock:
            return [
                {k: v for k, v in p.items() if not k.startswith("_")}
                for p in self.patterns
            ]

    def get_stats(self):
        with self._lock:
            total = len(self.patterns)
            active = sum(1 for p in self.patterns if p.get("active", True))
            reinforced = sum(1 for p in self.patterns if int(p.get("evidence_count", 1)) >= 2)
            return {
                "total_patterns": total,
                "active_patterns": active,
                "reinforced_patterns": reinforced,
                "file_path": str(self.patterns_file),
            }

    def clear_all(self):
        with self._lock:
            self.patterns = []
            self._invalidate_cache()
            self._save_patterns()
            logger.warning("BehavioralPatternEngine: all patterns cleared.")

    def shutdown(self):
        try:
            self._prune_stale_candidates()
            self._save_patterns()
            logger.info("BehavioralPatternEngine shutdown complete.")
        except Exception as e:
            logger.error(f"BehavioralPatternEngine shutdown error: {e}")


behavioral_pattern_engine = BehavioralPatternEngine()