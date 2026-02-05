from __future__ import annotations
import logging
import asyncio
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
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
            curr = MUSIC_CATALOG
            for k in keys:
                if k in curr:
                    curr = curr[k]
                elif "children" in curr and k in curr["children"]:
                    curr = curr["children"][k]
                else:
                    raise KeyError(f"Invalid path key: {k}")
            
            target_query = curr.get("query", "top hits")
            target_name = curr.get("name", "Genre")
            
            await query.delete_message()
            await _do_radio(update.effective_chat.id, target_query, context, name=target_name)
        except Exception as e:
            logger.error(f"Error processing play_cat callback: {e}")
            await _do_radio(update.effective_chat.id, "top hits", context, name="🎶 Топ Хиты")

    elif data == "main_menu_genres":
        await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard())
        
    elif data == "play_random":
        await query.delete_message()
        await _do_radio(update.effective_chat.id, "random", context, name="🎲 Random Mix")

# --- Background Worker Functions ---

async def _do_ai_chat_background(chat_id: int, text: str, user_name: str, context: ContextTypes.DEFAULT_TYPE):
    """Handles AI chat in the background."""
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    mode = context.chat_data.get("mode", "default")
    response = await ChatManager.get_response(text, user_name, mode)
    await context.bot.send_message(chat_id, response, reply_markup=get_persistent_menu())


async def _do_search_background(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE):
    """Handles music search and download in the background."""
    tracks = await context.application.downloader.search(query, limit=1)
    if not tracks:
        await context.bot.send_message(chat_id, f"❌ По запросу '{query}' ничего не найдено.", reply_markup=get_persistent_menu())
        return

    track = tracks[0]
    await context.bot.send_message(chat_id, f"⬇️ Загружаю: *{track.title}*...", parse_mode=ParseMode.MARKDOWN, reply_markup=get_persistent_menu())

    dl_result = await context.application.downloader.download(track.identifier, track)
    if dl_result and dl_result.success:
        try:
            with open(dl_result.file_path, 'rb') as f:
                keyboard = None
                if context.application.settings.BASE_URL:
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎧 Веб-плеер", url=context.application.settings.BASE_URL)
                    ]])

                await context.bot.send_audio(
                    chat_id,
                    audio=f,
                    caption=f"▶️ *{dl_result.track_info.title}*\n👤 {dl_result.track_info.uploader}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
        finally:
            try:
                os.unlink(dl_result.file_path)
            except Exception as e:
                logger.warning(f"Failed to delete downloaded file: {e}")
    else:
        await context.bot.send_message(chat_id, "❌ Не удалось скачать аудио для этого трека.", reply_markup=get_persistent_menu())


# --- TEXT HANDLER (Кнопки и Чат) ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text: return

    # --- Button Handling ---
    if text == "📻 Выбрать Жанр":
        await menu_command(update, context)
        return
    if text == "⏭ Skip":
        await context.application.radio_manager.skip(chat_id)
        await update.message.reply_text("⏭ Скипаю трек...", disable_notification=True, reply_markup=get_persistent_menu())
        return
    if text == "🛑 Стоп":
        await context.application.radio_manager.stop(chat_id)
        await update.message.reply_text("🛑 Эфир остановлен.", reply_markup=get_persistent_menu())
        return
    if text == "🎲 Случайная волна":
        await _do_radio(chat_id, "random", context, name="🎲 Случайная волна")
        return

    # --- AI Intent Analysis (Still blocking, but faster than the actions) ---
    analysis = await analyze_message(text)
    intent = analysis['intent']
    query = analysis['query']
    
    # --- Offload slow tasks to background ---
    if intent == 'chat':
        asyncio.create_task(
            _do_ai_chat_background(chat_id, text, update.effective_user.first_name, context)
        )

    elif intent == 'radio':
        await _do_radio(chat_id, query, context, name=query)
        
    elif intent == 'search':
        await update.message.reply_text(f"✅ Принято! Ищу трек: *{query}*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_persistent_menu())
        asyncio.create_task(
            _do_search_background(chat_id, query, context)
        )

def setup_handlers(app, radio, settings, downloader, spotify_service):
    app.downloader = downloader
    app.radio_manager = radio
    app.spotify_service = spotify_service
    app.settings = settings
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))