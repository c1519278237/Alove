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
    media_storage_dir: str = "./data/media"
    media_max_bytes: int = 10 * 1024 * 1024
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ]
    )

    ai_provider: str = "deepseek"
    ai_base_url: str = "https://api.deepseek.com/v1"
    ai_api_key: str | None = None
    ai_model: str = "deepseek-chat"
    ai_timeout_seconds: float = 30.0
    ai_max_tokens: int = 800
    ai_temperature: float = 0.35
    ai_input_cost_per_million_usd: float = 0.0
    ai_output_cost_per_million_usd: float = 0.0
    ai_daily_request_limit: int = 200
    ai_daily_token_limit: int = 200_000
    ai_min_interval_seconds: float = 1.0

    embedding_provider: str = "local_hash"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 384
    embedding_timeout_seconds: float = 30.0

    voice_provider: str = "device_tts"
    voice_webhook_url: str | None = None
    voice_webhook_token: str | None = None
    voice_timeout_seconds: float = 60.0
    voice_max_text_chars: int = 500
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_voice_model: str = "qwen3-tts-vc-2026-01-22"
    knowledge_max_bytes: int = 10 * 1024 * 1024

    sms_provider: str = "console"
    sms_webhook_url: str | None = None
    sms_webhook_token: str | None = None
    sms_timeout_seconds: float = 10.0
    sms_min_interval_seconds: int = 60
    sms_hourly_limit: int = 10
    sms_code_ttl_seconds: int = 300
    access_token_ttl_minutes: int = 60
    background_jobs_enabled: bool = True
    report_scheduler_interval_seconds: int = 3600

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
