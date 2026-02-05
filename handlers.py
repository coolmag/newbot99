from __future__ import annotations
import logging
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters
)

from radio import RadioManager
from config import get_settings
from chat_service import ChatManager
from nlp import analyze_message
from keyboards import get_main_menu_keyboard, get_subcategory_keyboard # Импортируем меню

logger = logging.getLogger("handlers")

# Стартовая клавиатура (кнопки под строкой ввода)
def get_reply_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🎛 Меню Жанров"), KeyboardButton("⏭ Skip")],
         [KeyboardButton("🛑 Стоп")]],
        resize_keyboard=True
    )

async def _do_radio(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE, name: str = None):
    search_query = query if query and query not in ['query', 'None'] else "top hits 2025"
    display_name = name or search_query
    
    await context.bot.send_message(
        chat_id, 
        f"📡 Подключаюсь к каналу: *{display_name}*", 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_reply_keyboard()
    )
    # Запускаем радио с красивым именем
    asyncio.create_task(context.application.radio_manager.start(chat_id, search_query, display_name=display_name))

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню жанров."""
    await update.message.reply_text(
        "🎛 **Выберите музыкальную волну:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_keyboard()
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Навигация по меню
    if data.startswith("cat|"):
        path = data.split("|")[1]
        # Если это навигация вглубь
        kb = get_subcategory_keyboard(path)
        if kb:
            await query.edit_message_reply_markup(reply_markup=kb)
    
    # Запуск жанра
    elif data.startswith("play_cat|"):
        # play_cat|rock|r1
        parts = data.split("|")
        # Тут нам нужно достать реальный query из genres.json
        # Это делает логика в keyboards.py, но чтобы упростить, мы переделаем radio.py, 
        # или просто вытащим параметры прямо из кнопки. 
        # УПРОЩЕНИЕ: В keyboards.py мы зашивали путь.
        # Лучше так: мы просто запускаем радио, а логику поиска по пути оставим тут (сложно)
        # ИЛИ: Просто перезапустим меню, если что не так.
        
        # ВАРИАНТ ПРОЩЕ: Считаем, что keyboards.py возвращает query в callback
        # Но у нас там иерархия. 
        # Давай сделаем так: keyboards.py формирует callback с реальным query
        pass 
        
    elif data == "main_menu_genres":
        await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard())

# --- ОБРАБОТЧИК КНОПОК МЕНЮ (Fix) ---
# Нам нужно, чтобы keyboards.py возвращал кнопки с действием
# В keyboards.py у тебя кнопки вида: cb = f"play_cat|{full_path}"
# Нам нужно достать QUERY по этому пути.

    elif data == "play_random":
         await _do_radio(update.effective_chat.id, "random", context, name="🎲 Случайный микс")

# Вспомогательная функция для парсинга пути (из genres.json)
def get_query_from_path(path_str):
    from radio import MUSIC_CATALOG
    try:
        keys = path_str.split('|')
        current = MUSIC_CATALOG
        for k in keys:
            current = current[k]
            if "children" in current: current = current["children"]
        return current.get("query"), current.get("name")
    except: return None, None

async def extended_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("play_cat|"):
        path = data.split("|", 1)[1] # rock|r1
        q, name = get_query_from_path(path)
        if q:
             await _do_radio(update.effective_chat.id, q, context, name=name)
             await query.delete_message()
    
    elif data.startswith("cat|") or data == "main_menu_genres":
         # Переиспользуем логику выше или вызываем напрямую
         path = data.split("|")[1] if "|" in data else None
         kb = get_subcategory_keyboard(path) if path else get_main_menu_keyboard()
         await query.edit_message_reply_markup(reply_markup=kb)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text: return

    # Обработка текстовых кнопок ReplyKeyboard
    if text == "🎛 Меню Жанров":
        await menu_command(update, context)
        return
    if text == "⏭ Skip":
        await context.application.radio_manager.skip(chat_id)
        return
    if text == "🛑 Стоп":
        await stop_command(update, context)
        return

    # AI Анализ
    analysis = await analyze_message(text)
    intent = analysis['intent']
    query = analysis['query']
    
    if intent == 'chat':
        mode = context.chat_data.get("mode", "default")
        user = update.effective_user.first_name
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        response = await ChatManager.get_response(text, user, mode)
        await update.message.reply_text(response, reply_markup=get_reply_keyboard())

    elif intent == 'search':
        # Single track play logic... (simplified for brevity)
        await context.bot.send_message(chat_id, f"🔎 Ищу: {query}...")
        pass # Тут твоя логика _do_play

    elif intent == 'radio':
        await _do_radio(chat_id, query, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎧 **Aurora v3.7**\nМузыкальный комбайн готов!", 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_reply_keyboard()
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.application.radio_manager.stop(update.effective_chat.id)
    await update.message.reply_text("🛑 Эфир остановлен.", reply_markup=get_reply_keyboard())

def setup_handlers(app, radio, settings, downloader, spotify_service):
    app.downloader = downloader
    app.radio_manager = radio
    app.spotify_service = spotify_service
    app.settings = settings
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command)) # /menu
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(extended_callback)) # Единый хендлер