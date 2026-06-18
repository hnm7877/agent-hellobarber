from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="agent-hellobarber", alias="APP_NAME")
    app_env: str = Field(default="production", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8001, alias="APP_PORT")

    ollama_base_url: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.2:latest", alias="OLLAMA_MODEL")
    ollama_timeout: int = Field(default=180, alias="OLLAMA_TIMEOUT")

    api_shared_token: str = Field(default="change_me_strong_token", alias="API_SHARED_TOKEN")
    allowed_origins: str = Field(default="*", alias="ALLOWED_ORIGINS")
    log_level: str = Field(default="info", alias="LOG_LEVEL")

    nestjs_base_url: str = Field(default="http://127.0.0.1:7700", alias="NESTJS_BASE_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def allowed_origins_list(self) -> List[str]:
        if not self.allowed_origins.strip():
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
