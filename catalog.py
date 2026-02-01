import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def load_catalog():
    """Загружает структуру жанров из genres.json"""
    json_path = Path(__file__).parent / "genres.json"
    try:
        if not json_path.exists():
            logger.error("❌ genres.json not found!")
            return {}
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"❌ Failed to load genres.json: {e}")
        return {}

# 1. Загружаем сырые данные (для radio.py)
FULL_CATALOG = load_catalog()

# 2. Адаптер для совместимости со старым кодом (keyboards.py)
def _convert_to_legacy(data):
    result = {}
    # Пытаемся найти корень меню, если структура сложная
    root = data.get("main_menu", {}).get("children", data)
    
    if not root: return {}

    for key, val in root.items():
        # Обработка структуры
        if isinstance(val, dict):
            # Если это ссылка на другой раздел (action=navigate)
            target_key = val.get("value", key)
            target_data = data.get(target_key, val) # Ищем в корне или берем текущий
            
            cat_name = target_data.get("name", key)
            children = target_data.get("children", {})
            
            result[cat_name] = {}
            for sub_k, sub_v in children.items():
                if isinstance(sub_v, dict):
                    name = sub_v.get("name", sub_k)
                    query = sub_v.get("query", "")
                    if query:
                        result[cat_name][name] = query
    return result

MUSIC_CATALOG = _convert_to_legacy(FULL_CATALOG)
