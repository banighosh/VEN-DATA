"""Application settings, read from environment variables.

Every setting has a safe default so the API starts locally without a .env file;
production values come from docker-compose / the hosting environment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "Meridian BI"
    version: str = "1.0.0"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://bi:bi@localhost:5432/bi"
    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = 100
    profile_row_limit: int = 250_000
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"])
    frame_cache_size: int = 8
    # Optional AI interpretation layer. Statistical insights never depend on it.
    anthropic_api_key: str | None = None
    insights_llm_model: str = "claude-sonnet-5-5"
    insights_llm_enabled: bool = False
    insights_llm_timeout_s: float = 25.0


@lru_cache
def get_settings() -> Settings:
    api_key = os.getenv("ANTHROPIC_API_KEY") or None
    return Settings(
        environment=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL", Settings.database_url),
        upload_dir=Path(os.getenv("UPLOAD_DIR", "./data/uploads")),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "100")),
        profile_row_limit=int(os.getenv("PROFILE_ROW_LIMIT", "250000")),
        cors_origins=_as_list(os.getenv("CORS_ORIGINS"), ["http://localhost:5173", "http://localhost:8080"]),
        frame_cache_size=int(os.getenv("FRAME_CACHE_SIZE", "8")),
        anthropic_api_key=api_key,
        insights_llm_model=os.getenv("INSIGHTS_LLM_MODEL", "claude-sonnet-5-5"),
        insights_llm_enabled=_as_bool(os.getenv("INSIGHTS_LLM_ENABLED"), default=bool(api_key)),
        insights_llm_timeout_s=float(os.getenv("INSIGHTS_LLM_TIMEOUT_S", "25")),
    )
