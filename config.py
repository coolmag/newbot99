from pathlib import Path
from typing import List, Any, Optional
from functools import lru_cache
import logging
import json
import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, ValidationInfo

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    
    BOT_TOKEN: str 
    WEBHOOK_URL: str = ""
    BASE_URL: str = ""
    
    # Ключи
    GOOGLE_API_KEY: str = Field(default="", validation_alias="GEMINI_API_KEY") # Алиас для Gemini
    OPENROUTER_API_KEY: str = ""

    # ВАЖНО: Алиас для ADMIN_IDS
    ADMIN_ID_LIST: Any = Field(default=[], validation_alias="ADMIN_IDS")
    
    # Пути
    BASE_DIR: Path = Path(__file__).resolve().parent
    DOWNLOADS_DIR: Path = BASE_DIR / "downloads"
    CACHE_DB_PATH: Path = BASE_DIR / "cache.db"
    
    LOG_LEVEL: str = "INFO"
    MAX_CONCURRENT_DOWNLOADS: int = 3

    @field_validator("GOOGLE_API_KEY", mode="before")
    @classmethod
    def _fallback_google_key(cls, v: Any) -> str:
        if v and str(v).strip(): return str(v)
        # Если пусто, ищем другие варианты
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")

    @field_validator("ADMIN_ID_LIST", mode="before")
    @classmethod
    def _assemble_admin_ids(cls, v: Any) -> List[int]:
        if not v: return []
        try: 
            # Обработка строки "123, 456"
            return [int(i.strip()) for i in str(v).split(",") if i.strip().isdigit()]
        except Exception as e:
            logger.error(f"Error parsing ADMIN_IDS: {e}")
            return []

@lru_cache()
def get_settings() -> Settings:
    return Settings()

RADIO_PRESETS = [
    "best pop hits 2024",
    "русские хиты новинки",
    "deep house relax",
    "rock classics hits",
    "lo-fi hip hop study",
    "энергичная музыка для тренировок",
    "вечерний джаз",
    "phonk playlist",
    "synthwave retrowave",
    "дискотека 90-х русская"
]
