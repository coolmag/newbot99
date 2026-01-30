from __future__ import annotations
import logging
import asyncio
import json
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters
)

from radio import RadioManager
from config import Settings, get_settings
from chat_service import ChatManager
from ai_personas import PERSONAS
from spotify import SpotifyService
from nlp import analyze_message

logger = logging.getLogger("handlers")

GREETINGS = {
    "default": ["Привет! Я снова я. 🎧", "Погнали!"],
    "toxic": ["Ну че, опять ты? 🙄"],
    "gop": ["Здарова, бродяга! 😎"],
    "chill": ["Вайб... 🌌"],
    "quiz": ["Викторина! 🎯"]
}

# --- ИСПОЛНИТЕЛИ ---

async def _do_spotify_play(chat_id: int, spotify_url: str, context: ContextTypes.DEFAULT_TYPE, update: Update):
    msg = await context.bot.send_message(chat_id, "🎶 Spotify link detected...", parse_mode=ParseMode.MARKDOWN)
    dl_res = await context.application.spotify_service.download_from_url(spotify_url)
    await msg.delete()

    if dl_res.success and dl_res.file_path:
        with open(dl_res.file_path, 'rb') as f:
            await context.bot.send_audio(chat_id=chat_id, audio=f, title=dl_res.track_info.title, performer=dl_res.track_info.artist)
    else:
        await context.bot.send_message(chat_id, f"❌ Ошибка: {dl_res.error_message}")

async def _do_play(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE, update: Update):
    msg = await context.bot.send_message(chat_id, f"🔎 Ищу: *{query}*...", parse_mode=ParseMode.MARKDOWN)
    tracks = await context.application.downloader.search(query, limit=1)

    if tracks:
        await msg.delete()
        dl_res = await context.application.downloader.download(tracks[0].identifier, tracks[0])
        if dl_res.success:
            with open(dl_res.file_path, 'rb') as f:
                await context.bot.send_audio(chat_id=chat_id, audio=f, title=tracks[0].title, performer=tracks[0].artist)
        else:
             await context.bot.send_message(chat_id, "❌ Не удалось скачать.")
    else:
        await msg.edit_text("❌ Ничего не найдено.")

async def _do_radio(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE, update: Update):
    # Если запрос пустой или 'query' (ошибка парсинга), ставим дефолт
    effective_query = query if query and query not in ['query', 'null', 'None'] else "случайные популярные треки"
    
    await context.bot.send_message(chat_id, f"🎧 Радио: *{effective_query}*", parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(context.application.radio_manager.start(chat_id, effective_query))

async def _do_chat_reply(chat_id: int, text: str, user_name: str, context: ContextTypes.DEFAULT_TYPE, update: Update):
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response = await ChatManager.get_response(chat_id, text, user_name)
    await update.message.reply_text(response)

# --- HANDLER ---

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text or len(text) < 2: return

    if "open.spotify.com/track" in text:
        await _do_spotify_play(chat_id, text, context, update)
        return

    intent = "chat"
    query = text

    try:
        # 🔥 АНАЛИЗ ИИ 🔥
        analysis = await analyze_message(text)
        
        # Проверяем, что вернулся словарь
        if isinstance(analysis, dict):
            intent = analysis.get("intent", "chat")
            query = analysis.get("query")
            # Если query пустой, используем исходный текст
            if not query: query = text 
        
        logger.info(f"[{chat_id}] FINAL DECISION: Intent='{intent}', Query='{query}'")
        
    except Exception as e:
        logger.error(f"NLP Error: {e}")

    # Логика роутинга
    if intent == 'radio':
        await _do_radio(chat_id, query, context, update)
    elif intent == 'search':
        await _do_play(chat_id, query, context, update)
    else:
        # Чат только в личке или по меншну
        is_direct = update.effective_chat.type == ChatType.PRIVATE or \
                    (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id) or \
                    any(w in text.lower() for w in ["аврора", "aurora", "бот"])
        
        if is_direct:
            await _do_chat_reply(chat_id, text, update.effective_user.first_name, context, update)

# --- SETUP ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎧 Aurora AI v3.0. Пиши жанр!")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Админка временно отключена.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.application.radio_manager.stop(update.effective_chat.id)
    await update.message.reply_text("🛑 Стоп.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    mode = ChatManager.get_mode(chat_id)
    await update.message.reply_text(f"📊 Статус:\n• Режим чата: {mode}\n• AI: Gemma 3 (Active)")

def setup_handlers(app, radio, settings, downloader, spotify_service):
    app.downloader = downloader
    app.radio_manager = radio
    app.spotify_service = spotify_service
    app.settings = settings
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_callback))
