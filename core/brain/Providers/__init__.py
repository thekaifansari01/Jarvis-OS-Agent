from core.brain.Providers.baseProvider import BaseLLMProvider
from core.brain.Providers.primaryProvider import PrimaryProvider
from core.brain.Providers.fallbackProvider import FallbackProvider
from core.logger.logger import logger


def get_primary_provider() -> BaseLLMProvider:
    logger.info("🔧 Initializing provider: PrimaryProvider")
    return PrimaryProvider()


def get_fallback_provider() -> BaseLLMProvider:
    logger.info("🔧 Initializing provider: FallbackProvider")
    return FallbackProvider()


__all__ = [
    "BaseLLMProvider",
    "PrimaryProvider",
    "FallbackProvider",
    "get_primary_provider",
    "get_fallback_provider",
]