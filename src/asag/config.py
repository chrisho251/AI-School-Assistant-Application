"""Centralized config — load from .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_db_url: str = ""

    # Self-hosted inference
    tei_embed_url: str = "http://localhost:8080"
    tei_rerank_url: str = "http://localhost:8081"

    # LLM
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    asag_llm_generator: str = "gemini/gemini-2.5-flash"
    asag_llm_judge: str = "groq/llama-3.3-70b-versatile"

    # Storage
    storage_backend: str = "supabase"  # supabase | r2
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "asag-sources"
    r2_endpoint: str = ""

    # Observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # App
    asag_env: str = "development"
    asag_log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
