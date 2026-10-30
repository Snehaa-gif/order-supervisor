from functools import lru_cache

from app.agent.llm.base import LLMClient, LLMError
from app.config import get_settings

__all__ = ["LLMClient", "LLMError", "get_llm"]


@lru_cache
def get_llm() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "mock":
        from app.agent.llm.mock import MockLLMClient

        return MockLLMClient()

    from app.agent.llm.gemini import GeminiClient

    return GeminiClient(
        api_key=settings.gemini_api_key,
        default_model=settings.gemini_model,
        fallback_models=settings.gemini_fallback_model_list,
    )
