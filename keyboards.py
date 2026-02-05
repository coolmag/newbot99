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
        
        # Start traversal from the root of the catalog data
        current = MUSIC_CATALOG
        
        # Follow the path of keys
        for key in keys:
            if key in current:
                current = current[key]
            elif "children" in current and key in current["children"]:
                current = current["children"][key]
            else:
                raise KeyError(f"Invalid path key: {key}")

        if "children" not in current:
            raise ValueError("Path does not lead to a category with children.")
            
        keyboard_items = current["children"]

        keyboard = []
        for key, val in keyboard_items.items():
            name = val.get("name", key)
            
            if "children" in val:
                 new_path = f"{path_str}|{key}"
                 keyboard.append([InlineKeyboardButton(f"📂 {name}", callback_data=f"cat|{new_path}")])
            else:
                 full_path = f"{path_str}|{key}"
                 keyboard.append([InlineKeyboardButton(f"▶️ {name}", callback_data=f"play_cat|{full_path}")])

        # Build the 'back' button path
        parent_path = "|".join(keys[:-1])
        back_callback = f"cat|{parent_path}" if parent_path else "main_menu_genres"
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=back_callback)])
        return InlineKeyboardMarkup(keyboard)

    except Exception as e:
        print(f"Keyboard Error: {e}")
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Ошибка меню", callback_data="main_menu_genres")]])