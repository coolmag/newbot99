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
    "default": ["Привет! Я снова я. 🎧"],
    "toxic": ["Ну че, опять ты? 🙄"],
    "gop": ["Здарова, бродяга! 😎"],
    "chill": ["Вайб... 🌌"],
    "quiz": ["Викторина! 🎯"]
}

# --- ЛОГИКА ---

async def _do_radio(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE, update: Update):
    # Если query пустой или технический мусор - ставим "top hits"
    search_query = query
    if not search_query or search_query in ['query', 'None', 'null']:
        search_query = "top hits 2025"
        
    await context.bot.send_message(chat_id, f"📡 Запускаю волну: *{search_query}*", parse_mode=ParseMode.MARKDOWN)
    
    # Запускаем радио (фоном)
    asyncio.create_task(context.application.radio_manager.start(chat_id, search_query))

async def _do_play(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE, update: Update):
    if not query:
        await context.bot.send_message(chat_id, "⚠️ Напиши название трека.")
        return

    msg = await context.bot.send_message(chat_id, f"🔎 Ищу: {query}...", parse_mode=ParseMode.MARKDOWN)
    
    # 1. Поиск
    tracks = await context.application.downloader.search(query, limit=1)
    
    if not tracks:
        await msg.edit_text("❌ Ничего не нашел.")
        return

    # 2. Скачивание
    await msg.edit_text(f"⬇️ Качаю: {tracks[0].title}...")
    dl_res = await context.application.downloader.download(tracks[0].identifier, tracks[0])
    
    await msg.delete()
    
    if dl_res.success:
        with open(dl_res.file_path, 'rb') as f:
            await context.bot.send_audio(chat_id=chat_id, audio=f, title=tracks[0].title, performer=tracks[0].artist)
    else:
        await context.bot.send_message(chat_id, "❌ Ошибка скачивания.")

async def _do_chat_reply(chat_id: int, text: str, user_name: str, context: ContextTypes.DEFAULT_TYPE, update: Update):
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response = await ChatManager.get_response(chat_id, text, user_name)
    await update.message.reply_text(response)

# --- ГЛАВНЫЙ ОБРАБОТЧИК ---

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text: return

    # AI Анализ
    intent = "chat"
    query = text
    
    try:
        analysis = await analyze_message(text)
        if isinstance(analysis, dict):
            intent = analysis.get("intent", "chat")
            query = analysis.get("query")
            if not query: query = text
            
        logger.info(f"[{chat_id}] AI: {intent} -> {query}")
    except: 
        pass

    # Роутинг
    if intent == 'radio':
        await _do_radio(chat_id, query, context, update)
    elif intent == 'search':
        await _do_play(chat_id, query, context, update)
    else:
        # Чат
        await _do_chat_reply(chat_id, text, update.effective_user.first_name, context, update)

# --- КОМАНДЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎧 Aurora Bot. Напиши жанр или название трека!")

async def radio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Команда /radio [запрос]
    query = " ".join(context.args) if context.args else "top hits"
    await _do_radio(update.effective_chat.id, query, context, update)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.application.radio_manager.stop(update.effective_chat.id)
    await update.message.reply_text("🛑 Радио остановлено.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Меню смены личности
    keyboard = []
    for mode in PERSONAS.keys():
        keyboard.append([InlineKeyboardButton(f"🎭 {mode.upper()}", callback_data=f"set_mode|{mode}")])
    keyboard.append([InlineKeyboardButton("❌ Закрыть", callback_data="close_admin")])
    
    await update.message.reply_text("⚙️ Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "close_admin":
        await query.delete_message()
    elif query.data.startswith("set_mode|"):
        mode = query.data.split("|")[1]
        ChatManager.set_mode(update.effective_chat.id, mode)
        await context.bot.send_message(update.effective_chat.id, f"✅ Режим: {mode}")

def setup_handlers(app, radio, settings, downloader, spotify_service):
    app.downloader = downloader
    app.radio_manager = radio
    app.spotify_service = spotify_service
    app.settings = settings
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("radio", radio_command)) # Добавил явную команду
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_callback))