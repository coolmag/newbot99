from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import json
from pathlib import Path

# Загружаем JSON один раз
with open(Path(__file__).parent / "genres.json", "r", encoding="utf-8") as f:
    MUSIC_CATALOG = json.load(f)

def get_main_menu_keyboard():
    """Главное меню (Категории верхнего уровня)"""
    keyboard = []
    # main_menu -> children
    root = MUSIC_CATALOG.get("main_menu", {}).get("children", {})
    
    for key, val in root.items():
        name = val.get("name", key)
        # cat|rock
        keyboard.append([InlineKeyboardButton(name, callback_data=f"cat|{key}")])
        
    return InlineKeyboardMarkup(keyboard)

def get_subcategory_keyboard(path_str: str):
    """Подменю"""
    try:
        keys = path_str.split('|')
        current = MUSIC_CATALOG["main_menu"]["children"]
        
        # Идем вглубь по ключам
        # Пример path: rock
        for k in keys:
            if k in current:
                current = current[k]
                if "children" in current:
                    current = current["children"]
            else:
                return None # Ошибка пути

        keyboard = []
        for key, val in current.items():
            name = val.get("name", key)
            
            # Если есть children -> это папка -> cat|rock|classic
            if "children" in val:
                 new_path = f"{path_str}|{key}"
                 keyboard.append([InlineKeyboardButton(f"📂 {name}", callback_data=f"cat|{new_path}")])
            # Иначе -> это жанр -> play_cat|rock|r1
            else:
                 full_path = f"{path_str}|{key}"
                 keyboard.append([InlineKeyboardButton(f"▶️ {name}", callback_data=f"play_cat|{full_path}")])

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu_genres")])
        return InlineKeyboardMarkup(keyboard)

    except Exception as e:
        print(f"Keyboard Error: {e}")
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Ошибка меню", callback_data="main_menu_genres")]])