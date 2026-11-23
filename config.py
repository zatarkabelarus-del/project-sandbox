import json
import os
from enum import Enum
from pathlib import Path
from functools import lru_cache
from typing import Any
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
BILLING_TARIFFS_PATH: Path = CONFIGS_DIR / "billing_tariffs.json"
MODELS_CATALOG_PATH: Path = CONFIGS_DIR / "models_catalog.json"


def load_models_catalog() -> dict[str, Any]:
    """Загружает внешний каталог графических нейросетей по абсолютному пути."""
    if MODELS_CATALOG_PATH.exists():
        with MODELS_CATALOG_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return {
        "default_model": "nanobanana-flash",
        "models": [
            {
                "id": "nanobanana-flash",
                "name": "NanoBanana (Gemini 2.5 Flash Image)",
                "provider_hint": "cloud_api",
                "cost_multiplier": 1.0,
                "badge_ru": "Базовая",
                "badge_en": "Standard",
                "description_ru": "Базовая модель генерации.",
                "description_en": "Standard generation model.",
                "is_active": True,
            }
        ],
    }


def get_model_cost_multiplier(model_id: str | None) -> float:
    """Возвращает тарифный мультипликатор выбранной модели (по умолчанию 1.0)."""
    if not model_id:
        return 1.0
    catalog = load_models_catalog()
    target = model_id.strip().lower()
    for item in catalog.get("models", []):
        if str(item.get("id", "")).strip().lower() == target:
            return max(0.5, float(item.get("cost_multiplier", 1.0)))
    return 1.0


class Settings(BaseSettings):
    app_mode: AppMode = AppMode.DEV_MOCK
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    master_key: str = "dev-mock-master-key-do-not-use-in-prod-32b"
    daily_budget_limit_usd: float = 50.00
    admin_email: str = ""
    jwt_expire_hours: int = 168

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
