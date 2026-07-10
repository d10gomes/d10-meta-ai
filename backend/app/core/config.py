import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

# Procurar .env na pasta do projeto (raiz), não na pasta atual
_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # backend/app/core/config.py -> raiz
_ENV_FILE = _ROOT / ".env"
if not _ENV_FILE.exists():
    _ENV_FILE = Path(os.getcwd()).parent / ".env"  # fallback


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me"
    APP_DEBUG: bool = True
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/d10"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Meta API
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_API_VERSION: str = "v21.0"
    META_CONFIG_ID: str = ""  # Facebook Login for Business config_id

    # WhatsApp
    WHATSAPP_API_URL: str = ""
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_DEFAULT_NUMBER: str = ""

    # JWT
    JWT_SECRET: str = "change-me-jwt"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # Scheduler
    SCANNER_INTERVAL_MINUTES: int = 30
    DOCTOR_INTERVAL_MINUTES: int = 60
    REPORT_CRON: str = "0 8 * * *"

    # Frontend URL (para OAuth redirect)
    NEXT_PUBLIC_API_URL: str = "http://localhost:8000"

    # Limits
    MAX_META_ACCOUNTS: int = 100


settings = Settings()
