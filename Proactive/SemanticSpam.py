import threading
from core.brain.Memory.LifetimeMemory import ltm_engine
from scipy.spatial.distance import cosine

SPAM_ANCHORS = [
    "50% off",
    "buy now",
    "subscribe to our channel",
    "limited time offer",
    "dhamaka sale",
    "cashback offer",
    "promotional message",
    "click the link below to win",
    "lottery winner",
    "special discount",
    "mega clearance",
    "exclusive deal"
]

_spam_embeddings = []
_init_lock = threading.Lock()
_init_done = False
_cache = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 500


def _initialize_spam_vectors():
    global _spam_embeddings, _init_done
    if _init_done:
        return
    with _init_lock:
        if _init_done:
            return
        try:
            for phrase in SPAM_ANCHORS:
                emb = ltm_engine._get_embedding(phrase)
                if emb is not None:
                    _spam_embeddings.append(emb)
            _init_done = True
        except Exception:
            _init_done = False


def check_semantic_spam(text, threshold=0.82):
    if not text or not text.strip():
        return False

    try:
        _initialize_spam_vectors()
        if not _spam_embeddings:
            return False

        cache_key = text[:200].lower().strip()
        with _cache_lock:
            cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        text_emb = ltm_engine._get_embedding(text)
        if text_emb is None:
            return False

        result = False
        for spam_emb in _spam_embeddings:
            similarity = 1 - cosine(text_emb, spam_emb)
            if similarity >= threshold:
                result = True
                break

        with _cache_lock:
            if len(_cache) >= _CACHE_MAX:
                _cache.clear()
            _cache[cache_key] = result

        return result
    except Exception:
        return False