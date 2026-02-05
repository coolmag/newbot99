from __future__ import annotations
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters
)

from radio import RadioManager
from config import get_settings
from chat_service import ChatManager
from nlp import analyze_message
from keyboards import get_main_menu_keyboard, get_subcategory_keyboard

logger = logging.getLogger("handlers")

# --- ГЛАВНОЕ МЕНЮ (Кнопки) ---
def get_persistent_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📻 Выбрать Жанр"), KeyboardButton("⏭ Skip")],
            [KeyboardButton("🛑 Стоп"), KeyboardButton("🎲 Случайная волна")]
        ],
        resize_keyboard=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎧 **Aurora v3.8 System Online**\nУправляй музыкой через кнопки внизу!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_persistent_menu()
    )

async def _do_radio(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE, name: str = None):
    display_name = name or query
    await context.bot.send_message(
        chat_id, 
        f"📡 Подключение: *{display_name}*", 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_persistent_menu()
    )
    asyncio.create_task(
        context.application.radio_manager.start(chat_id, query, display_name=display_name)
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает каталог (Inline Buttons)"""
    await update.message.reply_text(
        "🎛 **Каталог частот:**",
        reply_markup=get_main_menu_keyboard()
    )

# --- CALLBACKS (Навигация по каталогу) ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("cat|"):
        path = data.split("|")[1]
        kb = get_subcategory_keyboard(path)
        if kb: await query.edit_message_reply_markup(reply_markup=kb)
    
    elif data.startswith("play_cat|"):
        # Парсим путь к жанру
        from radio import MUSIC_CATALOG
        try:
            path = data.split("|", 1)[1] 
            keys = path.split("|")
            curr = MUSIC_CATALOG["main_menu"]["children"]
            for k in keys:
                curr = curr[k] if "children" not in curr else curr["children"][k]
            
            target_query = curr.get("query", "top hits")
            target_name = curr.get("name", "Genre")
            
            await query.delete_message()
            await _do_radio(update.effective_chat.id, target_query, context, name=target_name)
        except Exception:
            await _do_radio(update.effective_chat.id, "top hits", context)

    elif data == "main_menu_genres":
        await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard())
        
    elif data == "play_random":
        await query.delete_message()
        await _do_radio(update.effective_chat.id, "random", context, name="🎲 Random Mix")

# --- TEXT HANDLER (Кнопки и Чат) ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text: return

    # КНОПКИ
    if text == "📻 Выбрать Жанр":
        await menu_command(update, context)
        return
    if text == "⏭ Skip":
        await context.application.radio_manager.skip(chat_id)
        return
    if text == "🛑 Стоп":
        await context.application.radio_manager.stop(chat_id)
        await update.message.reply_text("🛑 Эфир остановлен.", reply_markup=get_persistent_menu())
        return
    if text == "🎲 Случайная волна":
        await _do_radio(chat_id, "random", context, name="🎲 Случайная волна")
        return

    # AI / CHAT
    analysis = await analyze_message(text)
    intent = analysis['intent']
    query = analysis['query']
    
    if intent == 'chat':
        mode = context.chat_data.get("mode", "default")
        user = update.effective_user.first_name
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        response = await ChatManager.get_response(text, user, mode)
        await update.message.reply_text(response, reply_markup=get_persistent_menu())

    elif intent == 'radio':
        await _do_radio(chat_id, query, context)
        
    elif intent == 'search':
        await context.bot.send_message(chat_id, f"🔎 Ищу: {query}...", reply_markup=get_persistent_menu())
        tracks = await context.application.downloader.search(query, limit=1)
        if tracks:
            dl = await context.application.downloader.download(tracks[0].identifier, tracks[0])
            if dl.success:
                 with open(dl.file_path, 'rb') as f:
                    await context.bot.send_audio(chat_id, audio=f, title=dl.track_info.title, performer=dl.track_info.uploader)
                 try: dl.file_path.unlink()
                 except: pass
            else:
                 await context.bot.send_message(chat_id, "❌ Не найдено аудио.")
        else:
            await context.bot.send_message(chat_id, "❌ Не найдено описание.")

def setup_handlers(app, radio, settings, downloader, spotify_service):
    app.downloader = downloader
    app.radio_manager = radio
    app.spotify_service = spotify_service
    app.settings = settings
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))