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

    coach_model: str = "gpt-4.1-mini"
    vision_model: str = "gpt-4o-mini"
    comprobante_model: str = "gpt-4o-mini"
    transcription_model: str = "gpt-4o-mini-transcribe"

    session_limit: int = 50
    session_ttl_seconds: int = 60 * 60 * 24 * 30

    max_proactive_msgs_per_day: int = 4
    use_redis_task_queue: bool = True
    task_dispatcher_interval_seconds: int = 30

    rate_limit_per_minute: int = 10
    max_message_chars: int = 4000
    max_webhook_payload_bytes: int = 1_000_000

    free_daily_msg_limit: int = 25

    default_timezone: str = "America/Bogota"

    precio_starter_cop: int = 5000
    precio_pro_cop: int = 14990
    precio_elite_cop: int = 39990
    precio_lifetime_cop: int = 399000
    descuento_anual_pct: int = 20
    cupos_lifetime_total: int = 100
    cuenta_destino_pago: str = "300 123 4567"
    cuenta_destino_alt: str = "1234567890"
    monto_pago_tolerancia_cop: int = 500
    referido_dias_bonus: int = 30

    miniapp_url: HttpUrl | None = None
    landing_url: HttpUrl | None = None
    admin_url: HttpUrl | None = None
    realtime_ws_url: str | None = None

    fernet_key: SecretStr | None = None
    resend_api_key: SecretStr | None = None
    sentry_dsn: SecretStr | None = None
    plausible_domain: str | None = None

    canal_logros_id: int | None = None
    canal_pro_id: int | None = None

    # Auto-seed del primer admin del panel en el startup. Si la tabla `admins`
    # esta vacia y ambas variables estan seteadas, se crea un admin `super`.
    # Util en Railway para que el primer deploy quede con un admin listo.
    admin_seed_email: str | None = None
    admin_seed_password: SecretStr | None = None

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
