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

def _initialize_spam_vectors():
    global _spam_embeddings
    if not _spam_embeddings:
        for phrase in SPAM_ANCHORS:
            emb = ltm_engine._get_embedding(phrase)
            _spam_embeddings.append(emb)

_initialize_spam_vectors()

def check_semantic_spam(text, threshold=0.75):
    if not text or not text.strip():
        return False
    
    text_emb = ltm_engine._get_embedding(text)
    
    for spam_emb in _spam_embeddings:
        similarity = 1 - cosine(text_emb, spam_emb)
        if similarity >= threshold:
            return True
            
    return False