"""Configuracion central de EntrenadorAX (pydantic-settings v2)."""
from __future__ import annotations

import secrets
from typing import Literal

from pydantic import HttpUrl, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion central tipada y validada al startup."""

    env: Literal["dev", "prod", "test"] = "dev"

    telegram_token: SecretStr
    openai_api_key: SecretStr

    database_url: PostgresDsn
    redis_url: RedisDsn

    webhook_base_url: HttpUrl | None = None
    # En produccion DEBE setearse como env var; el default es solo para dev/test
    # (cada restart regenera el secret -> webhook caido tras deploy).
    webhook_secret: SecretStr = SecretStr(secrets.token_hex(32))

    developer_chat_id: int | None = None
    # JWT secret para Mini App. Separado del admin_token por seguridad.
    jwt_secret: SecretStr = SecretStr(secrets.token_urlsafe(32))
    admin_token: SecretStr = SecretStr(secrets.token_urlsafe(32))

    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_timeout: int = 10
    db_pool_recycle: int = 300

    session_limit: int = 20
    session_ttl_seconds: int = 60 * 60 * 24 * 30

    rate_limit_per_minute: int = 10
    max_message_chars: int = 4000
    max_webhook_payload_bytes: int = 1_000_000

    default_timezone: str = "America/Bogota"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_postgres_dsn(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            if v.startswith("postgresql://"):
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("webhook_secret", "admin_token", "jwt_secret", mode="after")
    @classmethod
    def _secret_obligatorio_en_prod(cls, v, info):
        env = info.data.get("env") if hasattr(info, "data") else None
        if env == "prod":
            raw = v.get_secret_value() if hasattr(v, "get_secret_value") else str(v)
            if not raw or len(raw) < 16:
                raise ValueError(
                    f"{info.field_name} debe setearse como env var en prod (default autogenerado se pierde tras deploy)"
                )
        return v

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)

    @property
    def redis_url_str(self) -> str:
        return str(self.redis_url)


settings = Settings()
