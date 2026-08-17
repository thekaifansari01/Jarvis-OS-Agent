import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ================================================================
# API KEYS
# ================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REGOLO_API_KEY = os.getenv("REGOLO_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_AI")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# ================================================================
# AGENTIC BRAIN PROVIDERS
# ================================================================
AGENT_PRIMARY_PROVIDER = os.getenv("AGENT_PRIMARY_PROVIDER", "regolo")
AGENT_FALLBACK_PROVIDER = os.getenv("AGENT_FALLBACK_PROVIDER", "gemini")

# ================================================================
# FAST BRAIN (OpenAI-compatible)
# ================================================================
FAST_BRAIN_API_KEY = os.getenv("FAST_BRAIN_API_KEY")
FAST_BRAIN_MODEL = os.getenv("FAST_BRAIN_MODEL")
FAST_BRAIN_ENDPOINT = os.getenv("FAST_BRAIN_ENDPOINT")

# ================================================================
# SEMANTIC ROUTER (OpenAI-compatible)
# ================================================================
ROUTER_API_KEY = os.getenv("ROUTER_API_KEY")
ROUTER_MODEL = os.getenv("ROUTER_MODEL")
ROUTER_ENDPOINT = os.getenv("ROUTER_ENDPOINT")

# ================================================================
# IMAGE GENERATION (OpenAI-compatible)
# ================================================================
IMAGE_GEN_API_KEY = os.getenv("IMAGE_GEN_API_KEY")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL", "dall-e-3")
IMAGE_GEN_ENDPOINT = os.getenv("IMAGE_GEN_ENDPOINT")

# ================================================================
# LTM EXTRACTION (OpenAI-compatible)
# ================================================================
LTM_EXTRACTION_API_KEY = os.getenv("LTM_EXTRACTION_API_KEY")
LTM_EXTRACTION_MODEL = os.getenv("LTM_EXTRACTION_MODEL")
LTM_EXTRACTION_ENDPOINT = os.getenv("LTM_EXTRACTION_ENDPOINT")

# ================================================================
# GEMINI MODELS
# ================================================================
GEMINI_AGENT_MODEL = "gemma-4-31b-it"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"

# ================================================================
# REGOLO (Legacy / Agentic Provider)
# ================================================================
REGOLO_BASE_URL = "https://api.regolo.ai/v1"
REGOLO_MODEL = "glm5.2"
REGOLO_THINKING_ENABLED = True

# ================================================================
# OPENROUTER
# ================================================================
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
OPENROUTER_THINKING_ENABLED = True

# ================================================================
# CUSTOM PROVIDER (Local / Ollama / LM Studio)
# ================================================================
CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")
CUSTOM_BASE_URL = os.getenv("CUSTOM_BASE_URL")
CUSTOM_MODEL = os.getenv("CUSTOM_MODEL", "llama3")
CUSTOM_THINKING_ENABLED = os.getenv("CUSTOM_THINKING_ENABLED", "False").lower() == "true"

# ================================================================
# IMAGE MODELS (FALLBACKS)
# ================================================================
FLUX_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
AI_HORDE_IMAGE_MODEL = "AlbedoBase XL (SDXL)"

# ================================================================
# MISC
# ================================================================
AGENT_PROACTIVE = "openai/gpt-oss-120b"
EDGE_TTS_VOICE = "hi-IN-MadhurNeural"

EMBEDDING_DIM = 768
DEEP_RESEARCH_TIMEOUT = 420
EMAIL_SUMMARY_MAX_TOKENS = 40

RAG_CHUNK_SIZE = 1500
RAG_CHUNK_OVERLAP = 200
RAG_TOP_K = 15
RAG_RECENCY_BOOST = 0.2

# ================================================================
# AGENT LOOP CONFIG
# ================================================================
CONFIG = {
    "AGENT_MAX_STEPS": 50,
    "AGENT_TIMEOUT": 1800,
    "AGENT_RETRY_LIMIT": 2,
    "AGENT_SCRATCHPAD_MAX_CHARS": 500000,
    "LOG_FILE": str(Path(__file__).resolve().parents[2] / "Data" / "jarvis.log"),
}