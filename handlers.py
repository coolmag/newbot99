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
from ai_personas import PERSONAS # Import personas to build the admin menu

logger = logging.getLogger("handlers")

# --- KEYBOARDS ---

def get_persistent_menu():
    """The main reply keyboard under the text input area."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📻 Выбрать Жанр"), KeyboardButton("⏭ Skip")],
            [KeyboardButton("🛑 Стоп"), KeyboardButton("🎲 Случайная волна")]
        ],
        resize_keyboard=True
    )

def get_admin_keyboard():
    """Builds the admin menu for changing AI persona."""
    # A simple mapping for button labels
    persona_labels = {
        "default": "Эстет", "standup": "Комик", "expert": "Эксперт", 
        "gop": "Пацанский", "toxic": "Токсик", "chill": "Философ"
    }
    keyboard = [
        [InlineKeyboardButton(f"Режим: {persona_labels.get(key, key)}", callback_data=f"set_mode|{key}")]
        for key in PERSONAS.keys()
    ]
    return InlineKeyboardMarkup(keyboard)

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "🎧 **Aurora AI System Online**\nУправляй музыкой через кнопки внизу!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_persistent_menu()
    )

async def radio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /radio [query] command."""
    query = " ".join(context.args) if context.args else "random"
    name = query if query != "random" else "🎲 Случайная волна"
    await _do_radio(update.effective_chat.id, query, context, name=name)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /menu command and 'Выбрать Жанр' button."""
    await update.message.reply_text(
        "🎛 **Каталог музыкальных частот:**",
        reply_markup=get_main_menu_keyboard()
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /admin command for persona management."""
    user_id = update.effective_user.id
    if user_id not in context.application.settings.ADMIN_ID_LIST:
        await update.message.reply_text("⛔️ Доступ запрещен.")
        return
    
    current_mode = context.chat_data.get("mode", "default")
    await update.message.reply_text(
        f"⚙️ **Меню администратора**\n\nВыберите характер для AI.\nТекущий режим: *{current_mode}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /status command."""
    # A simple status for now, can be expanded later
    await update.message.reply_text("✅ Бот онлайн. AI-модуль активен.")

# --- HELPER FUNCTIONS ---

async def _do_radio(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE, name: str = None):
    """Starts the radio session."""
    display_name = name or query
    # No need to send a message here, the calling function (or AI comment) does it.
    asyncio.create_task(
        context.application.radio_manager.start(chat_id, query, display_name=display_name)
    )

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
                    chat_id, audio=f,
                    caption=f"▶️ *{dl_result.track_info.title}*\n👤 {dl_result.track_info.uploader}",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
                )
        finally:
            try:
                os.unlink(dl_result.file_path)
            except Exception as e:
                logger.warning(f"Failed to delete downloaded file: {e}")
    else:
        await context.bot.send_message(chat_id, "❌ Не удалось скачать аудио для этого трека.", reply_markup=get_persistent_menu())

# --- MAIN HANDLERS ---

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("cat|"):
        path = data.split("|")[1]
        kb = get_subcategory_keyboard(path)
        if kb: await query.edit_message_reply_markup(reply_markup=kb)
    
    elif data.startswith("play_cat|"):
        from radio import MUSIC_CATALOG
        try:
            path = data.split("|", 1)[1] 
            keys = path.split("|")
            curr = MUSIC_CATALOG
            for k in keys:
                curr = curr[k] if "children" not in curr else curr["children"][k]
            
            target_query = curr.get("query", "top hits")
            target_name = curr.get("name", "Genre")
            
            await query.edit_message_text(f"📡 Подключаюсь к каналу: *{target_name}*", parse_mode=ParseMode.MARKDOWN)
            await _do_radio(update.effective_chat.id, target_query, context, name=target_name)
        except Exception as e:
            logger.error(f"Error processing play_cat callback: {e}")
            await query.edit_message_text("❌ Ошибка выбора жанра.")

    elif data.startswith("set_mode|"):
        user_id = query.from_user.id
        if user_id not in context.application.settings.ADMIN_ID_LIST:
            await query.answer("⛔️ Доступ запрещен.", show_alert=True)
            return

        new_mode = data.split("|")[1]
        current_mode = context.chat_data.get("mode", "default")

        if new_mode == current_mode:
            await query.answer("Этот режим AI уже активен.")
            return

        context.chat_data["mode"] = new_mode
        await query.answer(f"✅ Режим AI изменен на: {new_mode}")
        await query.edit_message_text(
            f"⚙️ **Меню администратора**\n\nТекущий режим: *{new_mode}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )

    elif data == "main_menu_genres":
        await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard())

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all text messages and reply keyboard buttons."""
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text: return

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
        await update.message.reply_text("🎲 Кручу барабан...", disable_notification=True)
        await _do_radio(chat_id, "random", context, name="🎲 Случайная волна")
        return

    mode = context.chat_data.get("mode", "default")
    analysis = await analyze_message(text, mode=mode)
    
    intent = analysis.get('intent')
    query_text = analysis.get('query')
    comment = analysis.get('comment')

    if comment:
        await update.message.reply_text(comment, parse_mode=ParseMode.MARKDOWN, reply_markup=get_persistent_menu())

    if intent == 'chat':
        if not comment: # If AI provided a comment, we don't need a second response
            asyncio.create_task(
                _do_ai_chat_background(chat_id, text, update.effective_user.first_name, context)
            )
    elif intent == 'radio':
        await context.bot.send_message(chat_id, f"📡 Подключаюсь к каналу: *{query_text}*", parse_mode=ParseMode.MARKDOWN)
        await _do_radio(chat_id, query_text, context, name=query_text)
    elif intent == 'search':
        asyncio.create_task(
            _do_search_background(chat_id, query_text, context)
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)


def setup_handlers(app, radio, settings, downloader):
    """Registers all handlers with the application."""
    # Register an error handler first
    app.add_error_handler(error_handler)
    
    app.downloader = downloader
    app.radio_manager = radio
    app.settings = settings
    
    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("radio", radio_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("admin", admin_command))

    # Other Handlers
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))