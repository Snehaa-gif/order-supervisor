"""Application settings, loaded from environment variables / backend/.env."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./order_supervisor.db"

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    task_queue: str = "order-supervisor"

    llm_provider: Literal["gemini", "mock"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    # Tried in order when the primary model is busy or out of free-tier quota (HTTP 429/503/504).
    gemini_fallback_models: str = "gemini-3.5-flash-lite,gemini-flash-lite-latest,gemini-flash-latest,gemini-3.8-flash"

    @property
    def gemini_fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.gemini_fallback_models.split(",") if m.strip()]

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
