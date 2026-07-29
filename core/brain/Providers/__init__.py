from core.brain.Providers.baseProvider import BaseLLMProvider
from core.brain.Providers.geminiProvider import GeminiProvider
from core.brain.Providers.regoloProvider import RegoloProvider

from core.brain.config import AGENT_PRIMARY_PROVIDER, AGENT_FALLBACK_PROVIDER
from core.logger.logger import logger

def get_provider(provider_name: str = None) -> BaseLLMProvider:
    """
    Factory function to get an LLM provider instance.
    
    Args:
        provider_name: 'gemini' or 'regolo'. Defaults to AGENT_PRIMARY_PROVIDER.
    
    Returns:
        BaseLLMProvider instance
    
    Raises:
        ValueError: If provider is unknown or API key is missing.
    """
    provider_name = provider_name or AGENT_PRIMARY_PROVIDER
    provider_name = provider_name.lower()
    
    logger.info(f"🔧 Initializing provider: {provider_name}")
    
    if provider_name == "gemini":
        return GeminiProvider()
    elif provider_name == "regolo":
        return RegoloProvider()
    else:
        raise ValueError(f"❌ Unknown provider: {provider_name}. Choose 'gemini' or 'regolo'.")

def get_fallback_provider() -> BaseLLMProvider:
    """Get the fallback provider defined in config."""
    return get_provider(AGENT_FALLBACK_PROVIDER)

__all__ = [
    "BaseLLMProvider",
    "GeminiProvider", 
    "RegoloProvider",
    "get_provider",
    "get_fallback_provider"
]