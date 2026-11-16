import os
from enum import Enum
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(str, Enum):
    DEV_MOCK = "DEV_MOCK"
    CLOUD_API = "CLOUD_API"
    GPU_SERVER = "GPU_SERVER"


# Абсолютные пути относительно корня проекта
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
PROJECT_ROOT: Path = BACKEND_DIR.parent
LOCALES_DIR: Path = BACKEND_DIR / "locales"
CONFIGS_DIR: Path = BACKEND_DIR / "configs"


class Settings(BaseSettings):
    app_mode: AppMode = AppMode.DEV_MOCK
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    master_key: str = "dev-mock-master-key-do-not-use-in-prod-32b"
    daily_budget_limit_usd: float = 50.00

    database_url: str = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'local_dev.db').as_posix()}"
    redis_url: str = "redis://localhost:6379/0"
    default_locale: str = "ru"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    raw_mode = os.getenv("APP_MODE")
    if raw_mode:
        try:
            mode = AppMode(raw_mode.strip().upper())
        except ValueError:
            mode = AppMode.DEV_MOCK
        return Settings(app_mode=mode)
    return Settings()
