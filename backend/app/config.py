"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = Field("development", alias="APP_ENV")

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = Field("", alias="SUPABASE_URL")
    # Secret / service-role key — backend only; never expose to the frontend.
    supabase_secret_key: str = Field("", alias="SUPABASE_SECRET_KEY")

    # ── Gemini ────────────────────────────────────────────────────────────────
    # Server-side only; never put in VITE_ variables or frontend bundles.
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed browser origins.
    cors_origins_str: str = Field(
        "http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_str.split(",") if o.strip()]

    model_config = {"env_file": ".env", "populate_by_name": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
