from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "dev", "staging", "pilot", "production", "test"] = "local"
    app_name: str = "归音 API"
    app_secret_key: str = "guiyin-local-secret-change-me"
    app_encryption_key: str | None = None
    database_url: str = "sqlite:///./guiyin.db"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080"])

    ai_provider: str = "openai_compatible"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str | None = None
    ai_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: float = 30.0

    sms_provider: str = "console"
    sms_code_ttl_seconds: int = 300
    access_token_ttl_minutes: int = 60

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_local(self) -> bool:
        return self.app_env in {"local", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
