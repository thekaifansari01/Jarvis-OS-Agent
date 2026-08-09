import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REGOLO_API_KEY = os.getenv("REGOLO_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_AI")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

AGENT_PRIMARY_PROVIDER = os.getenv("AGENT_PRIMARY_PROVIDER", "regolo")
AGENT_FALLBACK_PROVIDER = os.getenv("AGENT_FALLBACK_PROVIDER", "gemini")

GROQ_FAST_MODEL = "llama-3.3-70b-versatile"
GROQ_SUMMARY_MODEL = "openai/gpt-oss-120b"

GEMINI_AGENT_MODEL = "gemma-4-31b-it"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"

REGOLO_BASE_URL = "https://api.regolo.ai/v1"
REGOLO_MODEL = "glm5.2"
REGOLO_THINKING_ENABLED = True

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
OPENROUTER_THINKING_ENABLED = True

CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")
CUSTOM_BASE_URL = os.getenv("CUSTOM_BASE_URL", "http://localhost:11434/v1")
CUSTOM_MODEL = os.getenv("CUSTOM_MODEL", "llama3")
CUSTOM_THINKING_ENABLED = os.getenv("CUSTOM_THINKING_ENABLED", "False").lower() == "true"

FLUX_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
AI_HORDE_IMAGE_MODEL = "AlbedoBase XL (SDXL)"

AGENT_PROACTIVE = "openai/gpt-oss-120b"
EDGE_TTS_VOICE = "hi-IN-MadhurNeural"

EMBEDDING_DIM = 768
DEEP_RESEARCH_TIMEOUT = 420
EMAIL_SUMMARY_MAX_TOKENS = 40

RAG_CHUNK_SIZE = 1500
RAG_CHUNK_OVERLAP = 200
RAG_TOP_K = 15
RAG_RECENCY_BOOST = 0.2

CONFIG = {
    "AGENT_MAX_STEPS": 50,
    "AGENT_TIMEOUT": 1800,
    "AGENT_RETRY_LIMIT": 2,
    "AGENT_SCRATCHPAD_MAX_CHARS": 500000,
    "LOG_FILE": str(Path(__file__).resolve().parents[2] / "Data" / "jarvis.log"),
}