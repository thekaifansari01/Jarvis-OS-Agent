import os
from dotenv import load_dotenv
load_dotenv()

GROQ_ROUTER_MODEL = "llama-3.1-8b-instant"
GROQ_FAST_MODEL = "llama-3.3-70b-versatile"
GROQ_SUMMARY_MODEL = "openai/gpt-oss-120b"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GEMINI_AGENT_MODEL = "gemma-4-31b-it"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

FLUX_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
TOGETHER_API_KEY = os.getenv("TOGETHER_AI")

AI_HORDE_IMAGE_MODEL = "AlbedoBase XL (SDXL)"

AGENT_PROACTIVE="openai/gpt-oss-120b"

EDGE_TTS_VOICE = "hi-IN-MadhurNeural"

EMBEDDING_DIM = 768

DEEP_RESEARCH_TIMEOUT = 420
EMAIL_SUMMARY_MAX_TOKENS = 40

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

CONFIG = {
    "AGENT_MAX_STEPS": 20,
    "AGENT_TIMEOUT": 900,
    "AGENT_RETRY_LIMIT": 2,
    "AGENT_SCRATCHPAD_MAX_CHARS": 500000,
}