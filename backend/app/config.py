"""Runtime settings. Secrets come from the environment, never from source."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    boxapi_api_key: str = ""
    boxapi_base_url: str = ""
    boxapi_model: str = ""
    database_path: str = "./data/starcoach.db"
    cors_origins: str = "*"
    stale_price_days: int = 30

    def cors_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw or raw == "*":
            return ["*"]
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.boxapi_api_key.strip() and self.boxapi_base_url.strip() and self.boxapi_model.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
