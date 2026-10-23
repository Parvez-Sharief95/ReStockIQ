"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = Field("development", alias="APP_ENV")

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = Field("", alias="SUPABASE_URL")
    # Secret / service-role key — backend only; never expose to the frontend.
    supabase_secret_key: str = Field("", alias="SUPABASE_SECRET_KEY")
    # Optional publishable / anon key for scoped user requests
    supabase_publishable_key: str = Field("", alias="SUPABASE_PUBLISHABLE_KEY")
    # Optional JWT secret for local cryptographic verification (HS256)
    supabase_jwt_secret: str = Field("", alias="SUPABASE_JWT_SECRET")

    # ── Storage & Repositories ───────────────────────────────────────────────
    # 'auto' (supabase in production, memory in test/dev), 'supabase', or 'memory'
    repository_backend: str = Field("auto", alias="REPOSITORY_BACKEND")

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

    @model_validator(mode="before")
    @classmethod
    def filter_frontend_vite_vars(cls, values: Any) -> Any:
        """Allow legitimate frontend VITE_* variables from shared root .env while catching misspelled backend settings."""
        if isinstance(values, dict):
            extracted = dict(values)
            if not extracted.get("SUPABASE_PUBLISHABLE_KEY") and extracted.get("VITE_SUPABASE_PUBLISHABLE_KEY"):
                extracted["SUPABASE_PUBLISHABLE_KEY"] = extracted["VITE_SUPABASE_PUBLISHABLE_KEY"]
            return {k: v for k, v in extracted.items() if not k.upper().startswith("VITE_")}
        return values

    model_config = {"env_file": ".env", "populate_by_name": True, "extra": "forbid"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
