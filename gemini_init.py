import os
import logging
import random
import asyncio
from typing import Optional
from google import genai
from google.genai import errors

logger = logging.getLogger("gemini")

# === ЗАГРУЗКА КЛЮЧЕЙ ===
def _load_keys():
    keys_str = os.getenv("GEMINI_API_KEYS", "")
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    if not keys:
        single = os.getenv("GEMINI_API_KEY", "")
        if single:
            keys.append(single.strip())
    return keys

KEYS = _load_keys()
HAS_GENAI = len(KEYS) > 0

if HAS_GENAI:
    logger.info(f"[Gemini] System active. Loaded {len(KEYS)} API keys. Rotation enabled.")
else:
    logger.warning("[Gemini] No API keys found. Gemini disabled.")

# === СТРАТЕГИЯ ВЫБОРА МОДЕЛИ (JAN 2026 UPDATE) ===
# На основе предоставленных данных:
# 2.5 Series - Stable (Основной выбор)
# 3 Series - Preview (Резерв для сложных задач)
# 2.0 Series - Deprecated (Удалить после 03.03.2026)

MODELS_PRIORITY = [
    "gemini-2.5-flash",       # STABLE: Быстрая, легкая, RPD ~500
    "gemini-3-flash",         # PREVIEW: Умная и быстрая
    "gemini-2.5-pro",         # STABLE: Мощная (контекст 1М)
    "gemini-2.0-flash",       # LEGACY: Запасной вариант (до марта 2026)
    "gemini-1.5-flash"        # FALLBACK: Старая рабочая лошадка
]

client_cache = {}

def get_client(api_key: str):
    if api_key not in client_cache:
        client_cache[api_key] = genai.Client(api_key=api_key)
    return client_cache[api_key]

def generate_smart(prompt: str) -> Optional[str]:
    """
    Генерирует ответ, используя ротацию ключей и приоритет моделей 2026 года.
    """
    if not HAS_GENAI:
        return None

    # Ротация ключей (Load Balancing)
    current_keys = list(KEYS)
    random.shuffle(current_keys)

    for api_key in current_keys:
        client = get_client(api_key)
        # Скрываем часть ключа для логов
        key_id = f"...{api_key[-4:]}" if len(api_key) > 4 else "???"
        
        for model_name in MODELS_PRIORITY:
            try:
                # logger.debug(f"[Gemini] Requesting {model_name} via {key_id}")
                
                response = client.models.generate_content(
                    model=model_name, 
                    contents=prompt
                )
                
                result = None
                if hasattr(response, 'text') and response.text:
                    result = response.text.strip()
                
                if result:
                    return result
                    
            except errors.ClientError as e:
                error_str = str(e)
                
                # Ошибка 429 (Лимит) -> Меняем КЛЮЧ
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    logger.warning(f"[Gemini] Rate Limit ({key_id}) on {model_name}. Switching key...")
                    break 
                
                # Ошибка 404 (Модель не найдена) -> Меняем МОДЕЛЬ (пробуем следующую на этом же ключе)
                if "404" in error_str or "Not Found" in error_str:
                    # logger.warning(f"[Gemini] Model {model_name} not found on this key. Trying next...")
                    continue
                
                logger.error(f"[Gemini] API Error {key_id} / {model_name}: {e}")
                break
                
            except Exception as e:
                logger.error(f"[Gemini] Critical error: {e}")
                break

    return None
