from core.brain.Providers.baseProvider import BaseLLMProvider
from core.brain.Providers.primaryProvider import PrimaryProvider
from core.brain.Providers.fallbackProvider import FallbackProvider


def get_provider(provider_name: str = "primary") -> BaseLLMProvider:
    name = (provider_name or "primary").strip().lower()
    if name in ("fallback", "fallbackprovider", "secondary"):
        return FallbackProvider()
    return PrimaryProvider()


__all__ = ["BaseLLMProvider", "PrimaryProvider", "FallbackProvider", "get_provider"]