import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "Data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip() or default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key, "").lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on", "enabled")


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except (ValueError, TypeError):
        return default


GEMINI_API_KEY     = _env("GEMINI_API_KEY")
TOGETHER_API_KEY   = _env("TOGETHER_AI")
TAVILY_API_KEY     = _env("TAVILY_API_KEY")


PRIMARY_API_KEY          = _env("PRIMARY_API_KEY")
PRIMARY_BASE_URL         = _env("PRIMARY_BASE_URL", "https://api.openai.com/v1")
PRIMARY_MODEL            = _env("PRIMARY_MODEL", "gpt-4o-mini")
PRIMARY_THINKING_ENABLED = _env_bool("PRIMARY_THINKING_ENABLED", True)

FALLBACK_API_KEY          = _env("FALLBACK_API_KEY")
FALLBACK_BASE_URL         = _env("FALLBACK_BASE_URL", "https://api.openai.com/v1")
FALLBACK_MODEL            = _env("FALLBACK_MODEL", "gpt-4o-mini")
FALLBACK_THINKING_ENABLED = _env_bool("FALLBACK_THINKING_ENABLED", True)

GEMINI_EMBEDDING_MODEL = _env("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")


FAST_BRAIN_API_KEY  = _env("FAST_BRAIN_API_KEY")
FAST_BRAIN_MODEL    = _env("FAST_BRAIN_MODEL", "gpt-4o-mini")
FAST_BRAIN_ENDPOINT = _env("FAST_BRAIN_ENDPOINT", "https://api.openai.com/v1")


ROUTER_API_KEY  = _env("ROUTER_API_KEY")
ROUTER_MODEL    = _env("ROUTER_MODEL", "gpt-4o-mini")
ROUTER_ENDPOINT = _env("ROUTER_ENDPOINT", "https://api.openai.com/v1")


IMAGE_GEN_API_KEY  = _env("IMAGE_GEN_API_KEY")
IMAGE_GEN_MODEL    = _env("IMAGE_GEN_MODEL", "dall-e-3")
IMAGE_GEN_ENDPOINT = _env("IMAGE_GEN_ENDPOINT", "https://api.openai.com/v1")

FLUX_IMAGE_MODEL     = _env("FLUX_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
AI_HORDE_IMAGE_MODEL = _env("AI_HORDE_IMAGE_MODEL", "AlbedoBase XL (SDXL)")


LTM_EXTRACTION_API_KEY  = _env("LTM_EXTRACTION_API_KEY")
LTM_EXTRACTION_MODEL    = _env("LTM_EXTRACTION_MODEL", "gpt-4o-mini")
LTM_EXTRACTION_ENDPOINT = _env("LTM_EXTRACTION_ENDPOINT", "https://api.openai.com/v1")


PROACTIVE_API_KEY  = _env("PROACTIVE_API_KEY")
PROACTIVE_MODEL    = _env("PROACTIVE_MODEL", "gpt-4o-mini")
PROACTIVE_ENDPOINT = _env("PROACTIVE_ENDPOINT", "https://api.openai.com/v1")

AGENT_PROACTIVE = _env("AGENT_PROACTIVE", "openai/gpt-oss-120b")


MEMORY_SUMMARY_API_KEY  = _env("MEMORY_SUMMARY_API_KEY")  or LTM_EXTRACTION_API_KEY
MEMORY_SUMMARY_MODEL    = _env("MEMORY_SUMMARY_MODEL")    or LTM_EXTRACTION_MODEL
MEMORY_SUMMARY_ENDPOINT = _env("MEMORY_SUMMARY_ENDPOINT") or LTM_EXTRACTION_ENDPOINT

MEMORY_RAW_RETENTION_DAYS         = _env_int("MEMORY_RAW_RETENTION_DAYS", 2)
MEMORY_SUMMARY_RETENTION_DAYS     = _env_int("MEMORY_SUMMARY_RETENTION_DAYS", 15)
MEMORY_SUMMARY_MIN_MESSAGES       = _env_int("MEMORY_SUMMARY_MIN_MESSAGES", 5)
MEMORY_SUMMARY_CATCHUP_ON_STARTUP = _env_bool("MEMORY_SUMMARY_CATCHUP_ON_STARTUP", True)
MEMORY_SUMMARY_MAX_CATCHUP_DAYS   = _env_int("MEMORY_SUMMARY_MAX_CATCHUP_DAYS", 15)


EMBEDDING_DIM     = 384
RAG_CHUNK_SIZE    = _env_int("RAG_CHUNK_SIZE", 1500)
RAG_CHUNK_OVERLAP = _env_int("RAG_CHUNK_OVERLAP", 200)
RAG_TOP_K         = _env_int("RAG_TOP_K", 15)
RAG_RECENCY_BOOST = _env_float("RAG_RECENCY_BOOST", 0.2)


EDGE_TTS_VOICE = _env("EDGE_TTS_VOICE", "hi-IN-MadhurNeural")


USER_NAME                = _env("USER_NAME", "Sir")
DEEP_RESEARCH_TIMEOUT    = _env_int("DEEP_RESEARCH_TIMEOUT", 420)
EMAIL_SUMMARY_MAX_TOKENS = _env_int("EMAIL_SUMMARY_MAX_TOKENS", 40)


CONFIG = {
    "AGENT_MAX_STEPS":            _env_int("AGENT_MAX_STEPS", 300),
    "AGENT_TIMEOUT":              _env_int("AGENT_TIMEOUT", 14400),
    "AGENT_RETRY_LIMIT":          _env_int("AGENT_RETRY_LIMIT", 4),
    "AGENT_SCRATCHPAD_MAX_CHARS": _env_int("AGENT_SCRATCHPAD_MAX_CHARS", 1000000),
    "LOG_FILE":                   str(DATA_DIR / "jarvis.log"),
}


def validate_config() -> list:
    missing = []

    if not FAST_BRAIN_API_KEY:
        missing.append("FAST_BRAIN_API_KEY")
    if not ROUTER_API_KEY:
        missing.append("ROUTER_API_KEY")
    if not LTM_EXTRACTION_API_KEY:
        missing.append("LTM_EXTRACTION_API_KEY")
    if not PROACTIVE_API_KEY:
        missing.append("PROACTIVE_API_KEY")
    if not MEMORY_SUMMARY_API_KEY:
        missing.append("MEMORY_SUMMARY_API_KEY (or LTM_EXTRACTION_API_KEY)")

    if not PRIMARY_API_KEY:
        missing.append("PRIMARY_API_KEY")
    if not FALLBACK_API_KEY:
        missing.append("FALLBACK_API_KEY")

    return missing


__all__ = [
    "PROJECT_ROOT", "DATA_DIR",
    "GEMINI_API_KEY",
    "TOGETHER_API_KEY", "TAVILY_API_KEY",
    "PRIMARY_API_KEY", "PRIMARY_BASE_URL", "PRIMARY_MODEL", "PRIMARY_THINKING_ENABLED",
    "FALLBACK_API_KEY", "FALLBACK_BASE_URL", "FALLBACK_MODEL", "FALLBACK_THINKING_ENABLED",
    "GEMINI_EMBEDDING_MODEL",
    "FAST_BRAIN_API_KEY", "FAST_BRAIN_MODEL", "FAST_BRAIN_ENDPOINT",
    "ROUTER_API_KEY", "ROUTER_MODEL", "ROUTER_ENDPOINT",
    "IMAGE_GEN_API_KEY", "IMAGE_GEN_MODEL", "IMAGE_GEN_ENDPOINT",
    "FLUX_IMAGE_MODEL", "AI_HORDE_IMAGE_MODEL",
    "LTM_EXTRACTION_API_KEY", "LTM_EXTRACTION_MODEL", "LTM_EXTRACTION_ENDPOINT",
    "PROACTIVE_API_KEY", "PROACTIVE_MODEL", "PROACTIVE_ENDPOINT",
    "AGENT_PROACTIVE",
    "MEMORY_SUMMARY_API_KEY", "MEMORY_SUMMARY_MODEL", "MEMORY_SUMMARY_ENDPOINT",
    "MEMORY_RAW_RETENTION_DAYS", "MEMORY_SUMMARY_RETENTION_DAYS",
    "MEMORY_SUMMARY_MIN_MESSAGES", "MEMORY_SUMMARY_CATCHUP_ON_STARTUP",
    "MEMORY_SUMMARY_MAX_CATCHUP_DAYS",
    "EMBEDDING_DIM", "RAG_CHUNK_SIZE", "RAG_CHUNK_OVERLAP",
    "RAG_TOP_K", "RAG_RECENCY_BOOST",
    "EDGE_TTS_VOICE", "USER_NAME",
    "DEEP_RESEARCH_TIMEOUT", "EMAIL_SUMMARY_MAX_TOKENS",
    "CONFIG", "validate_config",
]