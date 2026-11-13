import os
import re
import sys
import time
import math
import array
import shutil
import zipfile
import threading
import queue
import urllib.request
import pyaudio
import json
import webrtcvad
from collections import deque
from vosk import Model as VoskModel, KaldiRecognizer, SetLogLevel
from dotenv import load_dotenv

from core.logger.logger import logger
from core.voice.stt_status import update_stt_status
from core.voice import interrupt
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

load_dotenv()
SetLogLevel(-1)

AZURE_SPEECH_KEY = "fake_key_for_ondevice"
AZURE_SPEECH_REGION = "eastasia"
AZURE_KEYWORD_MODEL_PATH = "Data/model/azure/jarvis.table"
AZURE_TTS_VOICE = "hi-IN-MadhurNeural"

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

if not DEEPGRAM_API_KEY:
    logger.error("DEEPGRAM_API_KEY missing in .env file!")
else:
    logger.info("Deepgram API Key found.")

deepgram = DeepgramClient(DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY else None
update_stt_status("idle", "")

VOSK_MODEL_NAME = "vosk-model-small-en-in-0.4"
VOSK_MODEL_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL_NAME}.zip"
VOSK_MODEL_PATH = "Data/model/vosk-model-small"
VOSK_DOWNLOAD_DIR = "Data/model/_download"

MEMORY_DIR_PATH = "Data/jarvis_memory"
LTM_GRAPH_PATH = os.path.join(MEMORY_DIR_PATH, "lifetime_graph.json")
CHAT_HISTORY_PATH = os.path.join(MEMORY_DIR_PATH, "master_chat_history.jsonl")
DAILY_SUMMARIES_PATH = os.path.join(MEMORY_DIR_PATH, "daily_summaries.jsonl")


def download_vosk_model():
    os.makedirs(VOSK_DOWNLOAD_DIR, exist_ok=True)
    zip_path = os.path.join(VOSK_DOWNLOAD_DIR, f"{VOSK_MODEL_NAME}.zip")

    logger.info(f"Downloading Vosk model from {VOSK_MODEL_URL} ...")

    last_percent = [-1]

    def _reporthook(block_num, block_size, total_size):
        if total_size > 0:
            downloaded = block_num * block_size
            percent = min(100, downloaded * 100 // total_size)
            if percent != last_percent[0]:
                last_percent[0] = percent
                bar_length = 30
                filled = int(bar_length * percent // 100)
                bar = "█" * filled + "░" * (bar_length - filled)
                sys.stdout.write(f"\r  Vosk model download: [{bar}] {percent}%")
                sys.stdout.flush()

    try:
        urllib.request.urlretrieve(VOSK_MODEL_URL, zip_path, reporthook=_reporthook)
        sys.stdout.write("\n")
        sys.stdout.flush()
        logger.info("Vosk model download complete. Extracting...")

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(VOSK_DOWNLOAD_DIR)

        extracted_path = os.path.join(VOSK_DOWNLOAD_DIR, VOSK_MODEL_NAME)

        if not os.path.exists(extracted_path):
            for item in os.listdir(VOSK_DOWNLOAD_DIR):
                full = os.path.join(VOSK_DOWNLOAD_DIR, item)
                if os.path.isdir(full) and item.startswith("vosk-model"):
                    extracted_path = full
                    break

        if not os.path.exists(extracted_path):
            raise RuntimeError("Extracted Vosk model folder not found.")

        if os.path.exists(VOSK_MODEL_PATH):
            shutil.rmtree(VOSK_MODEL_PATH)

        os.makedirs(os.path.dirname(VOSK_MODEL_PATH), exist_ok=True)
        shutil.move(extracted_path, VOSK_MODEL_PATH)
        logger.info(f"Vosk model ready at: {VOSK_MODEL_PATH}")

    except Exception as e:
        sys.stdout.write("\n")
        sys.stdout.flush()
        logger.error(f"Failed to download Vosk model: {e}", exc_info=True)
        raise
    finally:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass
        if os.path.exists(VOSK_DOWNLOAD_DIR):
            try:
                shutil.rmtree(VOSK_DOWNLOAD_DIR)
            except Exception:
                pass


class DynamicVocabularyManager:
    TIER_0_SEEDS = {
        "Jarvis": 4,
        "Kaif": 4,
        "Ansari": 4,
        "Mindly": 3,
        "WhatsApp": 3,
        "Telegram": 3,
        "Gmail": 3,
        "Calendar": 2,
        "YouTube": 2,
        "Google": 2,
        "Chrome": 2,
        "GitHub": 3,
        "VSCode": 3,
        "Python": 3,
        "Pytest": 2,
        "Flask": 2,
        "FastAPI": 2,
        "React": 2,
        "Termux": 3,
        "Tailscale": 2,
        "Gemini": 3,
        "Llama": 2,
        "Regolo": 3,
        "OpenRouter": 2,
        "Ollama": 2,
        "Deepgram": 2,
        "Desktop": 2,
        "Documents": 2,
        "Downloads": 2,
        "Screenshot": 2,
        "Brightness": 2,
        "Volume": 2,
        "Bluetooth": 2,
        "WiFi": 2,
        "Kandhla": 3,
        "Muzaffarnagar": 2,
        "Shamli": 2,
    }

    DIRECT_PHONETIC_ALIASES = {
        "kaf": "kaif",
        "caf": "kaif",
        "kayf": "kaif",
        "qaif": "kaif",
        "kef": "kaif",
        "caif": "kaif",
        "kaiph": "kaif",
        "kefh": "kaif",
        "caff": "kaif",
        "kaff": "kaif",
        "ansaree": "ansari",
        "ansary": "ansari",
        "unsari": "ansari",
        "ansarii": "ansari",
        "jarviz": "jarvis",
        "jarves": "jarvis",
        "jaarvis": "jarvis",
        "watsapp": "whatsapp",
        "whatsap": "whatsapp",
        "githab": "github",
        "termax": "termux",
    }

    NAME_CONTEXT_TRIGGERS = {
        "cap", "cab", "calf", "cave", "chef", "safe", "case", "cash",
        "cast", "care", "camp", "cake", "cafe", "half", "kept", "cat"
    }

    PROTECTED_WORDS = {
        "the", "and", "for", "with", "this", "that", "from", "have", "what",
        "when", "where", "which", "who", "whom", "whose", "why", "how", "can",
        "cat", "car", "cap", "cab", "calf", "call", "care", "case", "cash",
        "cast", "card", "cart", "calm", "came", "camp", "cake", "cafe", "half",
        "safe", "save", "same", "name", "game", "time", "file", "files", "line",
        "code", "word", "words", "world", "worlds", "work", "works", "walk",
        "wall", "want", "warm", "wash", "watch", "water", "wave", "way", "week",
        "well", "went", "were", "west", "wheel", "while", "white", "whole",
        "wide", "wife", "wild", "will", "wind", "wine", "wing", "winter",
        "wire", "wise", "wish", "woman", "women", "wonder", "wood", "wool",
        "yard", "year", "yellow", "yes", "yesterday", "yet", "you", "young",
        "your", "zero", "zone", "open", "close", "start", "stop", "run", "make",
        "create", "delete", "remove", "send", "read", "write", "check", "find",
        "search", "play", "pause", "mute", "unmute", "lock", "unlock", "mail",
        "email", "message", "folder", "project", "app", "application", "system",
        "agent", "user", "info", "data", "unknown", "today", "tomorrow", "thing",
        "stuff", "hello", "okay", "thanks", "thank", "please", "sorry", "help",
        "mera", "meri", "mere", "naam", "hai", "hain", "hoon", "tha", "thi",
        "aur", "par", "lekin", "kya", "kaise", "kab", "kahan", "kyun", "isko",
        "usko", "apna", "apni", "bhai", "yaar", "ek", "do", "teen", "bhi", "toh",
        "nahi", "mat", "kar", "karo", "karna", "kardo", "bolo", "batao", "dekho",
        "suno", "chalo", "abhi", "aaj", "kal", "wala", "wali", "wale", "acha",
        "theek", "haan", "bhej", "bhejo", "khol", "kholo", "band", "chala", "chalao"
    }

    WORLD_LEFT_CONTEXT = {
        "hello", "whole", "real", "wide", "modern", "virtual", "digital",
        "entire", "outside", "around", "across", "save", "change", "rule",
        "open", "new", "old", "third", "first", "free", "material", "natural",
        "physical", "under", "dream", "fantasy", "future", "ancient", "best",
        "biggest", "largest", "fastest", "richest", "most"
    }

    WORLD_RIGHT_CONTEXT = {
        "cup", "war", "map", "record", "records", "wide", "bank", "health",
        "trade", "series", "tour", "champion", "championship", "peace",
        "population", "history", "economy", "news", "leader", "leaders",
        "order", "view", "famous", "class", "largest", "biggest", "best",
        "worst", "ending"
    }

    WORD_LEFT_CONTEXT = {
        "microsoft", "ms", "wake", "key", "pass", "code", "single", "every",
        "last", "one", "english", "hindi", "root", "buzz", "cross", "sight",
        "spoken", "written", "exact", "right", "wrong", "bad", "good", "swear",
        "curse", "magic", "secret", "another", "other", "each", "vocabulary"
    }

    WORD_RIGHT_CONTEXT = {
        "file", "files", "document", "documents", "doc", "docs", "docx",
        "count", "meaning", "meanings", "definition", "processor", "processing",
        "pad", "press", "wordpress", "list", "play", "search", "limit",
        "length", "boundary", "embeddings", "embedding", "vector", "token",
        "tokens", "level", "choice", "game", "puzzle", "format", "app"
    }

    def __init__(self):
        self._lock = threading.RLock()
        self._ltm_mtime = -1.0
        self._history_mtime = -1.0
        self._summary_mtime = -1.0
        self._ltm_entities = {}
        self._history_entities = {}
        self._summary_entities = {}
        self._merged_keywords = []
        self._known_proper_nouns = {}
        self._phonetic_index = {}
        self._rebuild_merged_state()

    @staticmethod
    def _phonetic_key(word):
        w = re.sub(r"[^a-z]", "", word.lower())
        if not w:
            return ""
        w = w.replace("ph", "f").replace("gh", "g").replace("kh", "k").replace("sh", "s").replace("ch", "c")
        w = w.replace("q", "k").replace("c", "k").replace("z", "s").replace("v", "w").replace("y", "i")
        w = re.sub(r"[aeiou]+", "a", w)
        dedup = [w[0]]
        for ch in w[1:]:
            if ch != dedup[-1]:
                dedup.append(ch)
        return "".join(dedup)

    @staticmethod
    def _edit_distance(s1, s2):
        if s1 == s2:
            return 0
        if len(s1) < len(s2):
            s1, s2 = s2, s1
        if not s2:
            return len(s1)
        prev_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row
        return prev_row[-1]

    def _is_valid_entity_token(self, token):
        if not token or not isinstance(token, str):
            return False
        clean = token.strip()
        if len(clean) < 3 or len(clean) > 20:
            return False
        if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", clean):
            return False
        low = clean.lower()
        if low in self.PROTECTED_WORDS:
            return False
        if low.isdigit():
            return False
        return True

    def _extract_entities_from_graph_file(self, path):
        extracted = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None

        if not isinstance(data, dict):
            return {}

        node_scores = {}
        for node_obj in data.get("nodes", []):
            if isinstance(node_obj, dict):
                node_id = str(node_obj.get("id", "")).strip()
                if node_id:
                    node_scores[node_id] = node_scores.get(node_id, 1.0)

        edges = data.get("links") or data.get("edges") or []
        for edge in edges:
            if not isinstance(edge, dict) or edge.get("archived", False):
                continue
            weight = float(edge.get("weight", 1) or 1)
            count = float(edge.get("count", 1) or 1)
            score_add = min(4.0, 1.0 + (weight * 0.4) + (count * 0.2))
            for key in ("source", "target"):
                val = str(edge.get(key, "")).strip()
                if val:
                    node_scores[val] = node_scores.get(val, 0.0) + score_add

            meta = edge.get("metadata")
            if isinstance(meta, dict):
                src_msg = str(meta.get("source_message", ""))
                if src_msg:
                    self._extract_from_text_into(src_msg, extracted, base_boost=3)

        for phrase, raw_score in node_scores.items():
            boost = 4 if raw_score >= 4.0 else (3 if raw_score >= 2.0 else 2)
            for part in re.findall(r"[A-Za-z]{3,20}", phrase):
                if self._is_valid_entity_token(part):
                    canon = part.capitalize()
                    if boost > extracted.get(canon, 0):
                        extracted[canon] = boost

        return extracted

    def _extract_from_text_into(self, text, target_dict, base_boost=3):
        if not text or not isinstance(text, str):
            return

        patterns = [
            r"(?:mera\s+naam|my\s+name\s+is|i\s+am|main\s+hoon|call\s+me)\s+([A-Za-z]{3,18}(?:\s+[A-Za-z]{3,18})?)",
            r"(?:mail|email|whatsapp|message|call)\s+(?:to\s+|karo\s+|kardo\s+)?([A-Za-z]{3,18})",
            r"([A-Za-z]{3,18})\s+(?:ko\s+mail|ko\s+whatsapp|ko\s+message|ko\s+call)",
        ]

        for pat in patterns:
            for match in re.finditer(pat, text, flags=re.IGNORECASE):
                group_val = match.group(1)
                for token in re.findall(r"[A-Za-z]{3,18}", group_val):
                    if self._is_valid_entity_token(token):
                        canon = token.capitalize()
                        target_dict[canon] = max(target_dict.get(canon, 0), base_boost)

        for cap_word in re.findall(r"\b[A-Z][a-z]{2,17}\b", text):
            if self._is_valid_entity_token(cap_word):
                target_dict[cap_word] = max(target_dict.get(cap_word, 0), 2)

    def _extract_entities_from_jsonl_file(self, path, field_name):
        extracted = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-120:]
        except Exception:
            return None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    text = str(obj.get(field_name, ""))
                    if text:
                        self._extract_from_text_into(text, extracted, base_boost=3)
            except Exception:
                continue

        return extracted

    def _rebuild_merged_state(self):
        combined = {}
        for word, boost in self.TIER_0_SEEDS.items():
            combined[word.lower()] = (word, int(boost))

        for source_dict in (self._ltm_entities, self._history_entities, self._summary_entities):
            for word, boost in source_dict.items():
                low = word.lower()
                if low in combined:
                    prev_word, prev_boost = combined[low]
                    combined[low] = (prev_word, max(prev_boost, int(boost)))
                else:
                    combined[low] = (word, int(boost))

        sorted_items = sorted(
            combined.values(),
            key=lambda item: (item[1], len(item[0])),
            reverse=True
        )[:65]

        self._merged_keywords = [f"{w}:{b}" for w, b in sorted_items]

        proper_nouns = {}
        phonetic_map = {}
        for w, b in sorted_items:
            low = w.lower()
            proper_nouns[low] = b
            if len(low) >= 4:
                pkey = self._phonetic_key(low)
                if pkey:
                    phonetic_map.setdefault(pkey, []).append(low)

        self._known_proper_nouns = proper_nouns
        self._phonetic_index = phonetic_map

    def refresh_if_needed(self):
        with self._lock:
            changed = False

            if os.path.exists(LTM_GRAPH_PATH):
                try:
                    mtime = os.path.getmtime(LTM_GRAPH_PATH)
                    if mtime != self._ltm_mtime:
                        res = self._extract_entities_from_graph_file(LTM_GRAPH_PATH)
                        if res is not None:
                            self._ltm_entities = res
                            self._ltm_mtime = mtime
                            changed = True
                except OSError:
                    pass
            elif self._ltm_mtime != -1.0 or self._ltm_entities:
                self._ltm_mtime = -1.0
                self._ltm_entities = {}
                changed = True

            if os.path.exists(CHAT_HISTORY_PATH):
                try:
                    mtime = os.path.getmtime(CHAT_HISTORY_PATH)
                    if mtime != self._history_mtime:
                        res = self._extract_entities_from_jsonl_file(CHAT_HISTORY_PATH, "message")
                        if res is not None:
                            self._history_entities = res
                            self._history_mtime = mtime
                            changed = True
                except OSError:
                    pass
            elif self._history_mtime != -1.0 or self._history_entities:
                self._history_mtime = -1.0
                self._history_entities = {}
                changed = True

            if os.path.exists(DAILY_SUMMARIES_PATH):
                try:
                    mtime = os.path.getmtime(DAILY_SUMMARIES_PATH)
                    if mtime != self._summary_mtime:
                        res = self._extract_entities_from_jsonl_file(DAILY_SUMMARIES_PATH, "summary")
                        if res is not None:
                            self._summary_entities = res
                            self._summary_mtime = mtime
                            changed = True
                except OSError:
                    pass
            elif self._summary_mtime != -1.0 or self._summary_entities:
                self._summary_mtime = -1.0
                self._summary_entities = {}
                changed = True

            if changed:
                self._rebuild_merged_state()

    def get_deepgram_keywords(self):
        self.refresh_if_needed()
        with self._lock:
            return list(self._merged_keywords)

    def select_best_transcript(self, alternatives):
        if not alternatives:
            return ""
        primary = getattr(alternatives[0], "transcript", "") or ""
        if not primary.strip() or len(alternatives) == 1:
            return primary

        with self._lock:
            known = self._known_proper_nouns

        def _score_candidate(alt, idx):
            txt = (getattr(alt, "transcript", "") or "").strip()
            if not txt:
                return -999.0
            conf = float(getattr(alt, "confidence", 0.85) or 0.85)
            tokens = re.findall(r"[a-zA-Z]+", txt.lower())
            entity_bonus = 0.0
            for t in tokens:
                if t in known:
                    entity_bonus += 0.06 * known[t]
                elif t in self.DIRECT_PHONETIC_ALIASES:
                    entity_bonus -= 0.05
            rank_penalty = idx * 0.03
            return conf + entity_bonus - rank_penalty

        best_alt = max(
            enumerate(alternatives[:3]),
            key=lambda item: _score_candidate(item[1], item[0])
        )[1]
        return getattr(best_alt, "transcript", "") or primary

    def _resolve_word_vs_world(self, tokens):
        n = len(tokens)
        if n == 0:
            return tokens

        out = list(tokens)
        for i, tok in enumerate(out):
            low = re.sub(r"[^a-z]", "", tok.lower())
            if low not in ("word", "world", "words", "worlds"):
                continue

            is_plural = low.endswith("s")
            prev_w = re.sub(r"[^a-z]", "", out[i - 1].lower()) if i > 0 else ""
            prev2_w = re.sub(r"[^a-z]", "", out[i - 2].lower()) if i > 1 else ""
            next_w = re.sub(r"[^a-z]", "", out[i + 1].lower()) if (i + 1) < n else ""

            target_base = None

            if prev_w in ("the", "this", "that", "my", "our") and prev2_w in (
                "in", "of", "around", "across", "over", "into", "throughout", "from", "to"
            ):
                if next_w not in self.WORD_RIGHT_CONTEXT:
                    target_base = "world"

            if target_base is None:
                if prev_w in self.WORLD_LEFT_CONTEXT or next_w in self.WORLD_RIGHT_CONTEXT:
                    target_base = "world"
                elif prev_w in self.WORD_LEFT_CONTEXT or next_w in self.WORD_RIGHT_CONTEXT:
                    target_base = "word"

            if target_base is not None:
                replacement = target_base + ("s" if is_plural else "")
                prefix = re.match(r"^[^a-zA-Z]*", tok).group(0)
                suffix = re.search(r"[^a-zA-Z]*$", tok).group(0)
                out[i] = f"{prefix}{replacement}{suffix}"

        return out

    def repair_transcript(self, text):
        if not text or not text.strip():
            return ""

        with self._lock:
            known_nouns = dict(self._known_proper_nouns)
            phonetic_idx = dict(self._phonetic_index)

        raw_tokens = text.strip().split()
        if not raw_tokens:
            return ""

        repaired = []
        n = len(raw_tokens)

        for i, raw_tok in enumerate(raw_tokens):
            prefix = re.match(r"^[^a-zA-Z0-9]*", raw_tok).group(0)
            suffix = re.search(r"[^a-zA-Z0-9]*$", raw_tok).group(0)
            core = raw_tok[len(prefix):len(raw_tok) - len(suffix)] if (len(prefix) + len(suffix)) < len(raw_tok) else raw_tok
            low = core.lower()

            if not low or not low.isalpha():
                repaired.append(raw_tok)
                continue

            if low in self.DIRECT_PHONETIC_ALIASES:
                fixed = self.DIRECT_PHONETIC_ALIASES[low]
                repaired.append(f"{prefix}{fixed}{suffix}")
                continue

            prev_low = re.sub(r"[^a-z]", "", raw_tokens[i - 1].lower()) if i > 0 else ""
            prev2_low = re.sub(r"[^a-z]", "", raw_tokens[i - 2].lower()) if i > 1 else ""
            next_low = re.sub(r"[^a-z]", "", raw_tokens[i + 1].lower()) if (i + 1) < n else ""

            is_name_context = (
                (prev_low == "naam" and prev2_low in ("mera", "apna"))
                or (prev_low == "is" and prev2_low == "name")
                or next_low in ("ansari", "ansaree", "ansary")
            )

            if is_name_context and (low in self.NAME_CONTEXT_TRIGGERS or self._edit_distance(low, "kaif") <= 2):
                repaired.append(f"{prefix}kaif{suffix}")
                continue

            if low in self.PROTECTED_WORDS or low in known_nouns or len(low) < 4:
                repaired.append(raw_tok)
                continue

            pkey = self._phonetic_key(low)
            candidates = phonetic_idx.get(pkey, [])
            best_match = None
            best_dist = 99

            for cand in candidates:
                if abs(len(cand) - len(low)) > 1:
                    continue
                dist = self._edit_distance(low, cand)
                max_allowed = 1 if len(cand) <= 6 else 2
                if dist <= max_allowed and dist < best_dist:
                    best_dist = dist
                    best_match = cand

            if best_match:
                repaired.append(f"{prefix}{best_match}{suffix}")
            else:
                repaired.append(raw_tok)

        repaired = self._resolve_word_vs_world(repaired)
        return " ".join(repaired).strip()


class UnifiedVoiceAssistant:
    def __init__(self):
        self.mic_available = False
        self.running = True
        self.command_queue = queue.Queue()
        self.vosk_recognizer = None
        self.audio = None
        self.stream = None
        self.dg_connection = None
        self.is_awake = False
        self.connection_established = False
        self._dg_session_id = 0
        self._vosk_silence_frames = 15
        self._vosk_speech_frames = 0
        self._vosk_partial_matched = False
        self._was_system_busy = False
        self.RATE = 16000
        self.CHUNK = 480

        self.use_azure_wake = False
        self.azure_speechsdk = None
        self.azure_speech_config = None
        self.azure_keyword_model = None
        self.azure_recognizer = None
        self.azure_push_stream = None
        self.azure_wake_detected = threading.Event()
        self.azure_needs_restart = threading.Event()
        self.azure_matched_text = "jarvis (azure)"

        self.frame_history = deque(maxlen=45)
        self._hp_prev_x = 0.0
        self._hp_prev_y = 0.0
        self._pre_prev_y = 0.0
        self._dg_hp_prev_x = 0.0
        self._dg_hp_prev_y = 0.0
        self._noise_floor_rms = 60.0
        self._agc_gain = 1.2
        self._last_reset_time = 0.0
        self.vocab_manager = DynamicVocabularyManager()

        try:
            self.vad = webrtcvad.Vad(2)
            self.strict_vad = webrtcvad.Vad(3)
            self.MAX_SILENCE_TIMEOUT = 1.0
            self.MAX_WAIT_TIMEOUT = 4.0
            self.MAX_TRANSCRIPT_IDLE_TIMEOUT = 1.8

            self.WAKE_WORDS = ["jarvis", "hey jarvis"]
            self.DECOY_WORDS = [
                "hello", "computer", "hi", "okay", "yes", "no", "stop",
                "test", "mike", "testing", "one",
                "two", "three", "alpha", "beta", "noise", "background", "something"
            ]

            self._init_wake_engine()

            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )

            self.current_transcript = ""
            self.live_text = ""
            self.command_done = threading.Event()
            self.last_speech_time = 0.0
            self.last_transcript_time = 0.0
            self.wake_time = 0.0
            self.first_speech_time = 0.0
            self.has_spoken = False

            self.mic_available = True
            logger.info("Microphone initialized successfully. Voice input ENABLED.")

        except Exception as e:
            self.mic_available = False
            logger.warning(f"Microphone not available — voice input DISABLED. Reason: {e}")

    @staticmethod
    def _is_input_popup_active():
        try:
            from core.main.HotKeyManager import is_popup_active
            return is_popup_active()
        except Exception:
            return False

    @staticmethod
    def _is_tts_or_processor_active():
        try:
            from core.voice import tts
            if tts.is_currently_speaking():
                return True
        except Exception:
            pass
        try:
            from core.main.CommandHandler import is_jarvis_busy
            if is_jarvis_busy():
                return True
        except Exception:
            pass
        return False

    def _init_wake_engine(self):
        if os.path.exists(AZURE_KEYWORD_MODEL_PATH):
            try:
                import azure.cognitiveservices.speech as speechsdk
                self.azure_speechsdk = speechsdk
                self.azure_speech_config = speechsdk.SpeechConfig(
                    subscription=AZURE_SPEECH_KEY,
                    region=AZURE_SPEECH_REGION
                )
                self.azure_keyword_model = speechsdk.KeywordRecognitionModel(AZURE_KEYWORD_MODEL_PATH)
                self.use_azure_wake = True
                logger.info(f"✅ Azure wake word engine ENABLED | model={AZURE_KEYWORD_MODEL_PATH}")
                return
            except Exception as e:
                logger.warning(f"⚠️ Azure wake word init failed: {e}. Falling back to Vosk.")
                self.use_azure_wake = False

        if not os.path.exists(VOSK_MODEL_PATH):
            logger.warning(f"Vosk model not found at '{VOSK_MODEL_PATH}'. Auto-downloading...")
            download_vosk_model()

        self.vosk_model = VoskModel(VOSK_MODEL_PATH)
        grammar = json.dumps(self.WAKE_WORDS + self.DECOY_WORDS + ["[unk]"])
        self.vosk_recognizer = KaldiRecognizer(self.vosk_model, self.RATE, grammar)
        try:
            self.vosk_recognizer.SetWords(True)
        except Exception:
            pass
        logger.info("✅ Vosk wake word engine ENABLED (fallback)")

    def _reset_dsp_state(self):
        self._hp_prev_x = 0.0
        self._hp_prev_y = 0.0
        self._pre_prev_y = 0.0
        self._vosk_silence_frames = 15
        self._vosk_speech_frames = 0
        self._vosk_partial_matched = False
        self.frame_history.clear()
        for _ in range(10):
            self.frame_history.append((False, False, 0.0, 0.0, 0.0))

    @staticmethod
    def _compute_raw_rms(pcm_data):
        samples = array.array("h")
        samples.frombytes(pcm_data)
        n_samples = len(samples)
        if n_samples == 0:
            return 0.0
        sum_sq = 0.0
        for s in samples:
            x = float(s)
            sum_sq += x * x
        return math.sqrt(sum_sq / n_samples)

    def _condition_deepgram_audio(self, pcm_data):
        samples = array.array("h")
        samples.frombytes(pcm_data)
        n_samples = len(samples)
        if n_samples == 0:
            return pcm_data

        hp_prev_x = self._dg_hp_prev_x
        hp_prev_y = self._dg_hp_prev_y
        hp_alpha = 0.967
        out_samples = array.array("h", [0] * n_samples)

        for i in range(n_samples):
            x = float(samples[i])
            hp_y = hp_alpha * (hp_prev_y + x - hp_prev_x)
            hp_prev_x = x
            hp_prev_y = hp_y
            val = int(hp_y)
            if val > 32767:
                val = 32767
            elif val < -32768:
                val = -32768
            out_samples[i] = val

        self._dg_hp_prev_x = hp_prev_x
        self._dg_hp_prev_y = hp_prev_y
        return out_samples.tobytes()

    def _analyze_and_condition_audio(self, pcm_data):
        try:
            is_speech_v2 = self.vad.is_speech(pcm_data, self.RATE)
        except Exception:
            is_speech_v2 = False

        try:
            is_speech_v3 = self.strict_vad.is_speech(pcm_data, self.RATE)
        except Exception:
            is_speech_v3 = False

        samples = array.array("h")
        samples.frombytes(pcm_data)
        n_samples = len(samples)
        if n_samples == 0:
            return pcm_data

        sum_sq = 0.0
        zero_crossings = 0
        prev_raw = samples[0]

        hp_prev_x = self._hp_prev_x
        hp_prev_y = self._hp_prev_y
        pre_prev_y = self._pre_prev_y
        hp_alpha = 0.967
        pre_coeff = 0.14

        filtered = [0.0] * n_samples

        for i in range(n_samples):
            x = float(samples[i])
            sum_sq += x * x
            if (x >= 0.0 and prev_raw < 0.0) or (x < 0.0 and prev_raw >= 0.0):
                zero_crossings += 1
            prev_raw = x

            hp_y = hp_alpha * (hp_prev_y + x - hp_prev_x)
            hp_prev_x = x
            hp_prev_y = hp_y

            out_y = hp_y - pre_coeff * pre_prev_y
            pre_prev_y = hp_y
            filtered[i] = out_y

        self._hp_prev_x = hp_prev_x
        self._hp_prev_y = hp_prev_y
        self._pre_prev_y = pre_prev_y

        raw_rms = math.sqrt(sum_sq / n_samples)
        zcr = zero_crossings / float(n_samples)

        if not is_speech_v3 and raw_rms < max(450.0, self._noise_floor_rms * 1.8):
            self._noise_floor_rms = (0.96 * self._noise_floor_rms) + (0.04 * max(25.0, raw_rms))

        if is_speech_v3 or raw_rms > (self._noise_floor_rms * 1.4):
            if raw_rms > 60.0:
                desired_gain = 2300.0 / raw_rms
                desired_gain = max(1.0, min(2.6, desired_gain))
                self._agc_gain = (0.75 * self._agc_gain) + (0.25 * desired_gain)
        else:
            self._agc_gain = (0.90 * self._agc_gain) + (0.10 * 1.0)

        gain = self._agc_gain
        out_samples = array.array("h", [0] * n_samples)
        cond_sum_sq = 0.0

        for i in range(n_samples):
            val = int(filtered[i] * gain)
            if val > 32767:
                val = 32767
            elif val < -32768:
                val = -32768
            out_samples[i] = val
            cond_sum_sq += float(val) * float(val)

        cond_rms = math.sqrt(cond_sum_sq / n_samples)
        self.frame_history.append((is_speech_v2, is_speech_v3, raw_rms, cond_rms, zcr))
        return out_samples.tobytes()

    def _extract_duration_ms(self, result):
        dur = getattr(result, "duration", 0)
        if hasattr(dur, "total_seconds"):
            return dur.total_seconds() * 1000.0
        if isinstance(dur, (int, float)) and dur > 0:
            if dur > 10000:
                return float(dur) / 10000.0
            return float(dur)
        return 0.0

    def _verify_wake_acoustics(self, text, duration_ms):
        now = time.time()
        if (now - self._last_reset_time) < 0.85:
            logger.debug("Wake rejected: post-reset cooldown active.")
            return False

        clean_text = (text or "").strip().lower()
        if clean_text and "jarvis" not in clean_text:
            logger.debug(f"Wake rejected: mismatched keyword text '{clean_text}'.")
            return False

        if duration_ms > 0.0 and (duration_ms < 210.0 or duration_ms > 1950.0):
            logger.debug(f"Wake rejected: invalid duration {duration_ms:.1f}ms.")
            return False

        frames = list(self.frame_history)
        if len(frames) < 6:
            return False

        v2_count = 0
        v3_count = 0
        max_contiguous_v2 = 0
        current_run = 0
        gap_allowance = 0
        speech_rms_values = []
        speech_zcr_values = []

        for is_v2, is_v3, raw_rms, cond_rms, zcr in frames:
            is_real_vocal = is_v3 or (is_v2 and raw_rms > max(110.0, self._noise_floor_rms * 1.25))
            if is_real_vocal:
                v2_count += 1
                current_run += 1
                gap_allowance = 0
                speech_rms_values.append(raw_rms)
                speech_zcr_values.append(zcr)
                if current_run > max_contiguous_v2:
                    max_contiguous_v2 = current_run
            else:
                if current_run > 0 and gap_allowance == 0:
                    gap_allowance = 1
                else:
                    current_run = 0
                    gap_allowance = 0
            if is_v3 and raw_rms > max(120.0, self._noise_floor_rms * 1.30):
                v3_count += 1

        if v2_count < 6 or v3_count < 2 or max_contiguous_v2 < 4:
            logger.debug(
                f"Wake rejected: insufficient VAD density "
                f"(v2={v2_count}, v3={v3_count}, run={max_contiguous_v2})."
            )
            return False

        if not speech_rms_values:
            return False

        peak_rms = max(speech_rms_values)
        mean_rms = sum(speech_rms_values) / len(speech_rms_values)
        mean_zcr = sum(speech_zcr_values) / len(speech_zcr_values)

        min_peak_required = max(145.0, self._noise_floor_rms * 1.40)
        min_mean_required = max(95.0, self._noise_floor_rms * 1.18)

        if peak_rms < min_peak_required or mean_rms < min_mean_required:
            logger.debug(
                f"Wake rejected: low vocal SNR "
                f"(peak={peak_rms:.1f}, mean={mean_rms:.1f}, floor={self._noise_floor_rms:.1f})."
            )
            return False

        if mean_zcr < 0.012 or mean_zcr > 0.46:
            logger.debug(f"Wake rejected: out-of-bounds ZCR ({mean_zcr:.3f}).")
            return False

        return True

    def _verify_azure_wake(self, text, duration_ms):
        return self._verify_wake_acoustics(text, duration_ms)

    def _evaluate_vosk_result_json(self, res_json_str):
        try:
            res = json.loads(res_json_str)
        except Exception:
            return False, ""

        text = (res.get("text") or "").strip().lower()
        if not self._check_wake_word(text):
            return False, ""

        duration_ms = float(self._vosk_speech_frames) * 30.0
        words = res.get("result")
        if isinstance(words, list) and words:
            jarvis_words = [
                w for w in words
                if isinstance(w, dict) and "jarvis" in str(w.get("word", "")).lower()
            ]
            if not jarvis_words:
                return False, ""
            best_w = max(jarvis_words, key=lambda w: float(w.get("conf", 0.0) or 0.0))
            conf = float(best_w.get("conf", 0.0) or 0.0)
            w_start = float(best_w.get("start", 0.0) or 0.0)
            w_end = float(best_w.get("end", 0.0) or 0.0)
            if w_end > w_start:
                duration_ms = (w_end - w_start) * 1000.0
            if conf < 0.58:
                logger.debug(f"Vosk wake rejected: low confidence ({conf:.2f}) for '{text}'.")
                return False, ""

        if self._vosk_speech_frames < 6:
            logger.debug(f"Vosk wake rejected: too few vocal frames ({self._vosk_speech_frames}).")
            return False, ""

        if not self._verify_wake_acoustics(text, duration_ms):
            return False, ""

        return True, text

    def _start_azure_listening(self):
        if not self.use_azure_wake or self.azure_speechsdk is None:
            return
        try:
            self._reset_dsp_state()
            audio_format = self.azure_speechsdk.audio.AudioStreamFormat(
                samples_per_second=self.RATE,
                bits_per_sample=16,
                channels=1
            )
            self.azure_push_stream = self.azure_speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
            audio_config = self.azure_speechsdk.AudioConfig(stream=self.azure_push_stream)

            self.azure_recognizer = self.azure_speechsdk.SpeechRecognizer(
                speech_config=self.azure_speech_config,
                audio_config=audio_config
            )

            def on_recognized(evt):
                if self.is_awake:
                    return
                if evt.result.reason == self.azure_speechsdk.ResultReason.RecognizedKeyword:
                    detected_text = getattr(evt.result, "text", "") or "jarvis"
                    duration_ms = self._extract_duration_ms(evt.result)
                    if self._verify_azure_wake(detected_text, duration_ms):
                        self.azure_matched_text = f"{detected_text} (azure)"
                        logger.info(
                            f"🎯 Azure wake word detected | text='{detected_text}' | duration={duration_ms:.0f}ms"
                        )
                        self.azure_wake_detected.set()
                    else:
                        self.azure_needs_restart.set()

            def on_canceled(evt):
                cancellation = evt.result.cancellation_details
                logger.debug(f"Azure keyword canceled | reason={cancellation.reason}")
                if not self.is_awake and not self.azure_wake_detected.is_set():
                    self.azure_needs_restart.set()

            self.azure_recognizer.recognized.connect(on_recognized)
            self.azure_recognizer.canceled.connect(on_canceled)
            self.azure_wake_detected.clear()
            self.azure_needs_restart.clear()
            self.azure_recognizer.start_keyword_recognition(self.azure_keyword_model)

            silence_preroll = b"\x00" * (self.CHUNK * 2 * 6)
            self.azure_push_stream.write(silence_preroll)
            logger.info("🎧 Azure keyword recognition started.")
        except Exception as e:
            logger.error(f"❌ Azure keyword recognition start failed: {e}")
            self.use_azure_wake = False

    def _stop_azure_listening(self):
        if self.azure_recognizer is not None:
            try:
                self.azure_recognizer.recognized.disconnect_all()
                self.azure_recognizer.canceled.disconnect_all()
                self.azure_recognizer.stop_keyword_recognition()
            except Exception as e:
                logger.debug(f"Azure recognizer stop error: {e}")
            finally:
                self.azure_recognizer = None

        if self.azure_push_stream is not None:
            try:
                self.azure_push_stream.close()
            except Exception:
                pass
            finally:
                self.azure_push_stream = None

        self.azure_wake_detected.clear()
        self.azure_needs_restart.clear()

    def start(self):
        if not self.mic_available:
            logger.warning("🎤 Mic not available. Skipping audio loop start.")
            return
        logger.info("🎧 Wake word listener thread starting...")
        self.listen_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.listen_thread.start()
        engine_name = "Azure (on-device)" if self.use_azure_wake else "Vosk"
        logger.info(f"✅ Wake word listener active | engine={engine_name} | word='Jarvis' / 'Hey Jarvis'")

    def play_wake_sound(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception as e:
            logger.error(f"Wake sound error: {e}")

    def _flush_audio_buffer(self):
        if not self.stream:
            return
        try:
            available = self.stream.get_read_available()
            if available > 0:
                self.stream.read(available, exception_on_overflow=False)
        except Exception as e:
            logger.error(f"Buffer flush error: {e}")

    def _setup_deepgram(self):
        self.current_transcript = ""
        self.live_text = ""
        self._dg_hp_prev_x = 0.0
        self._dg_hp_prev_y = 0.0
        self.command_done.clear()
        self._dg_session_id += 1
        active_session_id = self._dg_session_id
        assistant = self

        try:
            dynamic_keywords = self.vocab_manager.get_deepgram_keywords()
            self.dg_connection = deepgram.listen.websocket.v("1")

            def on_message(dg_self, result, **kwargs):
                if (
                    not assistant.is_awake
                    or assistant.command_done.is_set()
                    or active_session_id != assistant._dg_session_id
                ):
                    return
                alternatives = getattr(result.channel, "alternatives", None)
                if not alternatives:
                    return
                sentence = assistant.vocab_manager.select_best_transcript(alternatives)
                if sentence:
                    repaired_sentence = assistant.vocab_manager.repair_transcript(sentence)
                    prev_live = assistant.live_text
                    if result.is_final:
                        assistant.current_transcript = assistant.vocab_manager.repair_transcript(
                            (assistant.current_transcript + " " + repaired_sentence).strip()
                        )
                        assistant.live_text = assistant.current_transcript
                    else:
                        assistant.live_text = assistant.vocab_manager.repair_transcript(
                            (assistant.current_transcript + " " + repaired_sentence).strip()
                        )
                    if assistant.live_text.strip() and assistant.live_text != prev_live:
                        now_ts = time.time()
                        assistant.last_transcript_time = now_ts
                        assistant.last_speech_time = now_ts
                        assistant.has_spoken = True
                    if (
                        assistant.is_awake
                        and not assistant.command_done.is_set()
                        and active_session_id == assistant._dg_session_id
                    ):
                        update_stt_status("listening", assistant.live_text)

                if getattr(result, "speech_final", False) and assistant.live_text.strip():
                    assistant.command_done.set()

            def on_utterance_end(dg_self, utterance_end, **kwargs):
                if (
                    not assistant.is_awake
                    or assistant.command_done.is_set()
                    or active_session_id != assistant._dg_session_id
                ):
                    return
                if assistant.live_text.strip():
                    assistant.command_done.set()

            def on_error(dg_self, error, **kwargs):
                if active_session_id != assistant._dg_session_id or not assistant.is_awake:
                    return
                logger.error(f"Deepgram Error: {error}")
                assistant.command_done.set()

            self.dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
            self.dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
            self.dg_connection.on(LiveTranscriptionEvents.Error, on_error)

            options = LiveOptions(
                model="nova-2",
                language="hi",
                keywords=dynamic_keywords,
                smart_format=True,
                interim_results=True,
                vad_events=True,
                endpointing=800,
                utterance_end_ms="1000",
                encoding="linear16",
                channels=1,
                sample_rate=self.RATE,
            )

            if not self.dg_connection.start(options):
                logger.error("❌ Failed to start Deepgram websocket connection.")
                return False

            logger.info(f"🔗 Deepgram websocket connected | active_keywords={len(dynamic_keywords)}")
            return True

        except Exception as e:
            logger.error(f"❌ Deepgram setup exception: {e}", exc_info=True)
            return False

    def _check_wake_word(self, text):
        clean_text = (text or "").lower().strip()
        if not clean_text:
            return False
        return bool(re.search(r"\bjarvis\b", clean_text))

    def _audio_loop(self):
        if not self.mic_available:
            return

        if self.use_azure_wake:
            self._start_azure_listening()

        while self.running:
            try:
                pcm_data = self.stream.read(self.CHUNK, exception_on_overflow=False)

                if not self.is_awake:
                    if self._is_input_popup_active() or self._is_tts_or_processor_active():
                        self._was_system_busy = True
                        if self.azure_wake_detected.is_set():
                            self.azure_wake_detected.clear()
                        if self.vosk_recognizer and (self._vosk_speech_frames > 0 or self._vosk_silence_frames < 15):
                            self.vosk_recognizer.Reset()
                        self._vosk_speech_frames = 0
                        self._vosk_silence_frames = 15
                        self._vosk_partial_matched = False
                        self._last_reset_time = time.time()
                        continue

                    if self._was_system_busy:
                        self._was_system_busy = False
                        self._flush_audio_buffer()
                        self._reset_dsp_state()
                        if self.vosk_recognizer:
                            self.vosk_recognizer.Reset()
                        self._last_reset_time = time.time()
                        continue

                    conditioned_pcm = self._analyze_and_condition_audio(pcm_data)

                    if (time.time() - self._last_reset_time) < 0.85:
                        if self.azure_wake_detected.is_set():
                            self.azure_wake_detected.clear()
                        continue

                    triggered = False
                    matched_text = ""

                    if self.use_azure_wake:
                        if self.azure_needs_restart.is_set():
                            self.azure_needs_restart.clear()
                            self._stop_azure_listening()
                            self._start_azure_listening()

                        if self.azure_push_stream is not None:
                            try:
                                self.azure_push_stream.write(conditioned_pcm)
                            except Exception as e:
                                logger.error(f"Azure push stream write failed: {e}")
                                self._stop_azure_listening()
                                self._start_azure_listening()
                                continue

                        if self.azure_wake_detected.is_set():
                            triggered = True
                            matched_text = self.azure_matched_text
                            self.azure_wake_detected.clear()
                    else:
                        is_v2, is_v3, raw_rms, cond_rms, zcr = self.frame_history[-1]
                        is_vocal_frame = is_v3 or (is_v2 and raw_rms > max(125.0, self._noise_floor_rms * 1.35))

                        if is_vocal_frame:
                            self._vosk_silence_frames = 0
                            self._vosk_speech_frames += 1
                            if self.vosk_recognizer.AcceptWaveform(pcm_data):
                                ok, matched = self._evaluate_vosk_result_json(self.vosk_recognizer.Result())
                                if ok:
                                    triggered = True
                                    matched_text = matched
                                self.vosk_recognizer.Reset()
                                self._vosk_speech_frames = 0
                                self._vosk_partial_matched = False
                            else:
                                try:
                                    pres = json.loads(self.vosk_recognizer.PartialResult())
                                    ptext = pres.get("partial", "")
                                except Exception:
                                    ptext = ""
                                if self._check_wake_word(ptext):
                                    self._vosk_partial_matched = True
                        elif self._vosk_speech_frames > 0 and self._vosk_silence_frames < 15:
                            self._vosk_silence_frames += 1
                            if self.vosk_recognizer.AcceptWaveform(pcm_data):
                                ok, matched = self._evaluate_vosk_result_json(self.vosk_recognizer.Result())
                                if ok:
                                    triggered = True
                                    matched_text = matched
                                self.vosk_recognizer.Reset()
                                self._vosk_speech_frames = 0
                                self._vosk_silence_frames = 15
                                self._vosk_partial_matched = False
                            elif self._vosk_silence_frames >= 4 and self._vosk_partial_matched:
                                ok, matched = self._evaluate_vosk_result_json(self.vosk_recognizer.FinalResult())
                                if ok:
                                    triggered = True
                                    matched_text = matched
                                self.vosk_recognizer.Reset()
                                self._vosk_speech_frames = 0
                                self._vosk_silence_frames = 15
                                self._vosk_partial_matched = False
                            elif self._vosk_silence_frames >= 12:
                                ok, matched = self._evaluate_vosk_result_json(self.vosk_recognizer.FinalResult())
                                if ok:
                                    triggered = True
                                    matched_text = matched
                                self.vosk_recognizer.Reset()
                                self._vosk_speech_frames = 0
                                self._vosk_silence_frames = 15
                                self._vosk_partial_matched = False

                    if triggered:
                        logger.info(f"🎯 Wake word detected | matched_text='{matched_text}'")

                        try:
                            from core.voice import tts
                            tts.stop_speaking()
                        except Exception:
                            pass

                        interrupt.set_interrupt()
                        self._flush_audio_buffer()

                        if self.use_azure_wake:
                            self._stop_azure_listening()

                        if self.vosk_recognizer:
                            self.vosk_recognizer.Reset()
                        self._vosk_speech_frames = 0
                        self._vosk_silence_frames = 15
                        self._vosk_partial_matched = False

                        self.play_wake_sound()
                        update_stt_status("connecting", "Listening...")

                        if not self.connection_established or self.dg_connection is None:
                            logger.info("🔌 Establishing Deepgram connection...")
                            if self._setup_deepgram():
                                self.connection_established = True
                                logger.info("✅ Deepgram connection established.")
                            else:
                                logger.warning("⚠️ Deepgram connection failed. Returning to wake word mode.")
                                self.connection_established = False
                                self.is_awake = False
                                self.command_done.clear()
                                self._flush_audio_buffer()
                                self._reset_dsp_state()
                                self._last_reset_time = time.time()
                                update_stt_status("idle", "")
                                if self.use_azure_wake:
                                    self._start_azure_listening()
                                elif self.vosk_recognizer:
                                    self.vosk_recognizer.Reset()
                                continue

                        self._flush_audio_buffer()
                        self.command_done.clear()
                        now_ts = time.time()
                        self.wake_time = now_ts
                        self.first_speech_time = 0.0
                        self.last_speech_time = now_ts
                        self.last_transcript_time = 0.0
                        self.has_spoken = False
                        self.is_awake = True
                        logger.info("👂 User command listening STARTED (max wait 4.0s, silence timeout 1.0s).")
                        update_stt_status("listening", "Listening...")

                else:
                    if self._is_input_popup_active():
                        self._force_sleep_reset()
                        continue

                    raw_rms = self._compute_raw_rms(pcm_data)
                    try:
                        is_strict_speech = self.strict_vad.is_speech(pcm_data, self.RATE)
                    except Exception:
                        is_strict_speech = False

                    is_speech = is_strict_speech and (raw_rms > max(145.0, self._noise_floor_rms * 1.45))
                    current_time = time.time()

                    if is_speech:
                        if not self.has_spoken:
                            self.first_speech_time = current_time
                        self.last_speech_time = current_time
                        self.has_spoken = True

                    has_transcript = bool(self.live_text.strip())

                    if not has_transcript and (current_time - self.wake_time > self.MAX_WAIT_TIMEOUT):
                        logger.info("⏱️ No speech detected within 4.0s after wake word. Ending command capture.")
                        self.command_done.set()

                    elif has_transcript and (current_time - self.last_speech_time > self.MAX_SILENCE_TIMEOUT):
                        logger.info("⏱️ Silence timeout (1.0s) reached after speech. Finalizing command.")
                        self.command_done.set()

                    elif (
                        has_transcript
                        and self.last_transcript_time > 0.0
                        and (current_time - self.last_transcript_time > self.MAX_TRANSCRIPT_IDLE_TIMEOUT)
                    ):
                        logger.info("⏱️ Transcript idle timeout reached. Finalizing command.")
                        self.command_done.set()

                    if self.dg_connection and not self.command_done.is_set():
                        try:
                            clean_dg_pcm = self._condition_deepgram_audio(pcm_data)
                            self.dg_connection.send(clean_dg_pcm)
                        except Exception as e:
                            logger.error(f"❌ Lost Deepgram connection while sending audio: {e}")
                            self._force_sleep_reset()
                            continue

                    if self.command_done.is_set():
                        self.process_final_command()

            except Exception as e:
                logger.error(f"Audio loop error: {e}")
                time.sleep(0.01)

    def _force_sleep_reset(self):
        logger.warning("🔄 Force sleep reset triggered. Returning to wake word mode.")
        self.is_awake = False
        self.command_done.clear()
        self._dg_session_id += 1
        self.live_text = ""
        self.current_transcript = ""

        dg_conn = self.dg_connection
        self.dg_connection = None
        self.connection_established = False
        if dg_conn:
            try:
                dg_conn.finish()
            except Exception:
                pass

        self._flush_audio_buffer()
        self._reset_dsp_state()

        if self.vosk_recognizer:
            self.vosk_recognizer.Reset()

        if self.use_azure_wake:
            self._stop_azure_listening()
            self._start_azure_listening()

        self._last_reset_time = time.time()
        update_stt_status("idle", "")
        logger.info("💤 Back to idle. Listening for wake word...")

    def process_final_command(self):
        self.is_awake = False
        self.command_done.clear()
        self._dg_session_id += 1

        repaired_text = self.vocab_manager.repair_transcript(self.live_text)
        full_command = repaired_text.lower().strip()
        self.live_text = ""
        self.current_transcript = ""

        ignore_words = [
            "", "okay", "okay.", "jarvis", "jarvis.", "hey jarvis", "hey jarvis.",
            "thanks", "thank you", "hmm", "haan", "ah", "uh", "theek hai", "hello", "ha"
        ]

        logger.info("🛑 User command listening STOPPED. Processing transcript...")
        logger.info(f"📝 Raw transcript received: '{full_command}'")

        dg_conn = self.dg_connection
        self.dg_connection = None
        self.connection_established = False
        if dg_conn:
            try:
                dg_conn.finish()
            except Exception as e:
                logger.error(f"❌ Error finishing Deepgram connection: {e}")

        time.sleep(0.1)
        self._flush_audio_buffer()
        self._reset_dsp_state()

        if self.vosk_recognizer:
            self.vosk_recognizer.Reset()

        if self.use_azure_wake:
            self._stop_azure_listening()
            self._start_azure_listening()

        self._last_reset_time = time.time()
        interrupt.clear_interrupt()

        if full_command and full_command not in ignore_words and len(full_command) > 3:
            logger.info(f"✅ Valid command accepted -> '{full_command}'")
            update_stt_status("understanding", full_command)
            self.command_queue.put(full_command)
        else:
            logger.info("🚫 Command rejected (empty/ignore-list/too short) -> returning to wake mode.")
            update_stt_status("idle", "")
            self.command_queue.put("")

        logger.info("💤 Idle. Waiting for next wake word 'Jarvis'...")

    def get_command(self, is_retry=False):
        command = None
        while self.running:
            try:
                command = self.command_queue.get(timeout=0.5)
                break
            except queue.Empty:
                continue

        if not self.running or command is None:
            return ""

        if command:
            logger.info(f"📤 Command delivered to processor: '{command}'")

        return command

    def stop(self):
        logger.info("🛑 Stopping voice engine...")
        self.running = False
        self.is_awake = False
        self.command_done.set()
        self._dg_session_id += 1

        self._stop_azure_listening()

        dg_conn = self.dg_connection
        self.dg_connection = None
        self.connection_established = False
        if dg_conn:
            try:
                dg_conn.finish()
            except Exception:
                pass
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
        except Exception:
            pass
        try:
            if self.audio:
                self.audio.terminate()
        except Exception:
            pass
        logger.info("✅ Voice engine stopped.")


try:
    engine = UnifiedVoiceAssistant()
except Exception as e:
    logger.critical(f"Failed to initialize voice engine: {e}. Falling back to dummy engine.")

    class _DummyEngine:
        mic_available = False

        def __init__(self):
            self.mic_available = False
            self.running = False

        def start(self):
            pass

        def stop(self):
            pass

        def get_command(self, is_retry=False):
            return ""

    engine = _DummyEngine()


def start_background_wake_word_listener():
    engine.start()


def listen():
    if not getattr(engine, 'mic_available', False):
        return ""
    return engine.get_command()


if __name__ == "__main__":
    try:
        start_background_wake_word_listener()
        logger.info("Voice module ready")
        while True:
            command = listen()
            if command:
                pass
    except KeyboardInterrupt:
        engine.stop()
    except Exception as e:
        logger.error(f"Main loop fatal error: {e}", exc_info=True)
        engine.stop()