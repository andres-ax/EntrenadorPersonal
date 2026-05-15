from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_token: str = ""
    database_url: str = ""
    redis_url: str = ""
    openai_api_key: str = ""
    webhook_base_url: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
