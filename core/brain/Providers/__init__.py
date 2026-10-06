from core.brain.Providers.baseProvider import BaseLLMProvider
from core.brain.Providers.geminiProvider import GeminiProvider
from core.brain.Providers.regoloProvider import RegoloProvider
from core.brain.Providers.openrouterProvider import OpenRouterProvider
from core.brain.Providers.customProvider import CustomProvider

from core.brain.config import AGENT_PRIMARY_PROVIDER, AGENT_FALLBACK_PROVIDER
from core.logger.logger import logger

def get_provider(provider_name: str = None) -> BaseLLMProvider:
    provider_name = provider_name or AGENT_PRIMARY_PROVIDER
    provider_name = provider_name.lower()
    
    logger.info(f"🔧 Initializing provider: {provider_name}")
    
    if provider_name == "gemini":
        return GeminiProvider()
    elif provider_name == "regolo":
        return RegoloProvider()
    elif provider_name == "openrouter":
        return OpenRouterProvider()
    elif provider_name in ["custom", "openai", "ollama", "local"]:
        return CustomProvider()
    else:
        raise ValueError(f"❌ Unknown provider: {provider_name}. Choose 'gemini', 'regolo', 'openrouter', or 'custom'.")

def get_fallback_provider() -> BaseLLMProvider:
    return get_provider(AGENT_FALLBACK_PROVIDER)

__all__ = [
    "BaseLLMProvider",
    "GeminiProvider", 
    "RegoloProvider",
    "OpenRouterProvider",
    "CustomProvider",
    "get_provider",
    "get_fallback_provider"
]