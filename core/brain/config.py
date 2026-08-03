import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class ModelConfig(str):
    def __new__(cls, name: str, vision: bool = False, tools: bool = True, reasoning: bool = False):
        obj = super().__new__(cls, name)
        obj.vision = vision
        obj.tools = tools
        obj.reasoning = reasoning
        return obj

    @property
    def capabilities(self) -> dict:
        return {"vision": self.vision, "tools": self.tools, "reasoning": self.reasoning}

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REGOLO_API_KEY = os.getenv("REGOLO_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_AI")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

AGENT_PRIMARY_PROVIDER = os.getenv("AGENT_PRIMARY_PROVIDER", "regolo")
AGENT_FALLBACK_PROVIDER = os.getenv("AGENT_FALLBACK_PROVIDER", "gemini")

GROQ_FAST_MODEL = ModelConfig("llama-3.3-70b-versatile", vision=False, tools=True, reasoning=False)
GROQ_SUMMARY_MODEL = ModelConfig("openai/gpt-oss-120b", vision=False, tools=True, reasoning=False)

GEMINI_AGENT_MODEL = ModelConfig("gemma-4-31b-it", vision=True, tools=True, reasoning=True)
GEMINI_EMBEDDING_MODEL = ModelConfig("gemini-embedding-2", vision=False, tools=False, reasoning=False)

REGOLO_BASE_URL = "https://api.regolo.ai/v1"
REGOLO_MODEL = ModelConfig("glm5.2", vision=True, tools=True, reasoning=True)
REGOLO_THINKING_ENABLED = True

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = ModelConfig("nvidia/nemotron-3-ultra-550b-a55b:free", vision=False, tools=True, reasoning=True)
OPENROUTER_THINKING_ENABLED = True

FLUX_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
AI_HORDE_IMAGE_MODEL = "AlbedoBase XL (SDXL)"

AGENT_PROACTIVE = ModelConfig("openai/gpt-oss-120b", vision=False, tools=True, reasoning=False)
EDGE_TTS_VOICE = "hi-IN-MadhurNeural"

EMBEDDING_DIM = 768
DEEP_RESEARCH_TIMEOUT = 420
EMAIL_SUMMARY_MAX_TOKENS = 40

CONFIG = {
    "AGENT_MAX_STEPS": 50,
    "AGENT_TIMEOUT": 1800,
    "AGENT_RETRY_LIMIT": 2,
    "AGENT_SCRATCHPAD_MAX_CHARS": 500000,
    "LOG_FILE": str(Path(__file__).resolve().parents[2] / "Data" / "jarvis.log"),
}
