from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from catalog import MUSIC_CATALOG # Импорт из нового файла

def get_main_menu_keyboard():
    """Генерирует клавиатуру главного меню."""
    categories = list(MUSIC_CATALOG.keys())
    keyboard = []
    for cat in categories:
        # Используем полный путь в callback_data
        cb = f"cat|{cat}"
        keyboard.append([InlineKeyboardButton(cat, callback_data=cb)])
    keyboard.append([InlineKeyboardButton("🎲 Случайный микс", callback_data="play_random")])
    return InlineKeyboardMarkup(keyboard)

def get_subcategory_keyboard(path_str: str):
    """Генерирует клавиатуру для подкатегорий на основе полного пути."""
    try:
        path = path_str.split('|')
        current_level = MUSIC_CATALOG
        for p in path:
            current_level = current_level[p]
    except KeyError:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Ошибка меню", callback_data="main_menu")]])

    keyboard = []
    for name, val in current_level.items():
        # Сокращаем путь для кнопок, если он слишком длинный
        full_path = f"{path_str}|{name}"
        
        # Если это папка (dict)
        if isinstance(val, dict):
            cb = f"cat|{full_path}"
            if len(cb.encode()) <= 64:
                keyboard.append([InlineKeyboardButton(f"📂 {name}", callback_data=cb)])
        else:
            cb = f"play_cat|{full_path}"
            if len(cb.encode()) <= 64:
                keyboard.append([InlineKeyboardButton(f"▶️ {name}", callback_data=cb)])
            
    # Кнопка назад
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu_genres")])
        
    return InlineKeyboardMarkup(keyboard)

# ========= ФУНКЦИИ ДЛЯ ПОИСКА (ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ) =========
def get_track_search_keyboard(tracks, page: int = 1):
    """
    Генерирует клавиатуру с результатами поиска треков.
    """
    keyboard = []
    for idx, track in enumerate(tracks, start=1):
        title = getattr(track, "title", "")
        artist = getattr(track, "artist", "")
        duration = getattr(track, "duration", 0)
        mins, secs = divmod(duration, 60)
        text = f"{idx}. {artist} - {title} ({mins}:{secs:02d})" if artist else f"{idx}. {title} ({mins}:{secs:02d})"
        cb = f"sel_track|{getattr(track, 'identifier', idx)}"
        keyboard.append([InlineKeyboardButton(text, callback_data=cb)])
    return InlineKeyboardMarkup(keyboard)

def get_pagination_keyboard(current_page: int, total_pages: int, base_value: str):
    """
    Клавиатура для постраничной навигации в результатах поиска.
    """
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton("◀️", callback_data=f"page|{current_page-1}|{base_value}"))
    buttons.append(InlineKeyboardButton(f"📄 {current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("▶️", callback_data=f"page|{current_page+1}|{base_value}"))
    return InlineKeyboardMarkup([buttons])
