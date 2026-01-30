from pathlib import Path
from typing import List, Any, Optional, Union
from functools import lru_cache
import logging
import json
import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, ValidationInfo

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    
    BOT_TOKEN: str 
    WEBHOOK_URL: str = ""
    BASE_URL: str = ""
    
    # Ключи и доступы
    # Теперь автоматически подхватит GEMINI_API_KEY, если GOOGLE_API_KEY пуст
    GOOGLE_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None

    ADMIN_ID_LIST: List[int] = []
    
    # Пути
    BASE_DIR: Path = Path(__file__).resolve().parent
    DOWNLOADS_DIR: Path = BASE_DIR / "downloads"
    CACHE_DB_PATH: Path = BASE_DIR / "cache.db"
    
    # Настройки
    LOG_LEVEL: str = "INFO"
    MAX_CONCURRENT_DOWNLOADS: int = 3

    @field_validator("GOOGLE_API_KEY", mode="before")
    @classmethod
    def _fallback_google_key(cls, v: Any) -> str:
        # Если ключ пустой, пробуем взять GEMINI_API_KEY
        if v and str(v).strip():
            return str(v)
        return os.getenv("GEMINI_API_KEY", "")

    @field_validator("ADMIN_ID_LIST", mode="before")
    @classmethod
    def _assemble_admin_ids(cls, v: Any) -> List[int]:
        if not v: return []
        try: return [int(i.strip()) for i in str(v).split(",") if i.strip()]
        except: return []

@lru_cache()
def get_settings() -> Settings:
    return Settings()