from __future__ import annotations
import logging
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters
)

from radio import RadioManager
from config import get_settings
from chat_service import ChatManager
from ai_personas import PERSONAS
from spotify import SpotifyService
from nlp import analyze_message

logger = logging.getLogger("handlers")

# --- ЛОГИКА ---

async def _do_radio(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE):
    # Защита от пустых запросов и технических ошибок
    search_query = query
    if not search_query or search_query in ['query', 'None', 'null']:
        search_query = "top hits 2025"
        
    await context.bot.send_message(chat_id, f"📡 Радио-поток: *{search_query}*", parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(context.application.radio_manager.start(chat_id, search_query))

async def _do_play(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE):
    msg = await context.bot.send_message(chat_id, f"🔎 Ищу: {query}...", parse_mode=ParseMode.MARKDOWN)
    tracks = await context.application.downloader.search(query, limit=1)
    
    if not tracks:
        await msg.edit_text("❌ Пусто.")
        return

    await msg.delete()
    dl_res = await context.application.downloader.download(tracks[0].identifier, tracks[0])
    
    if dl_res.success:
        with open(dl_res.file_path, 'rb') as f:
            await context.bot.send_audio(chat_id=chat_id, audio=f, title=dl_res.track_info.title, performer=dl_res.track_info.artist)
    else:
        await context.bot.send_message(chat_id, "❌ Ошибка загрузки.")

# --- ГЛАВНЫЙ МОЗГ ---

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text: return

    # 1. Spotify Link
    if "open.spotify.com/track" in text:
        await context.bot.send_message(chat_id, "🎵 Spotify ссылка...")
        dl = await context.application.spotify_service.download_from_url(text)
        if dl.success:
            with open(dl.file_path, 'rb') as f:
                await context.bot.send_audio(chat_id=chat_id, audio=f, title=dl.track_info.title, performer=dl.track_info.artist)
        return

    # 2. AI Анализ
    analysis = await analyze_message(text)
    intent = analysis['intent']
    query = analysis['query']
    
    logger.info(f"🤖 AI Decided: {intent} -> {query}")

    # 3. Маршрутизация
    if intent == 'chat':
        # Чат: берем режим из context.chat_data (Best Practice 2026)
        mode = context.chat_data.get("mode", "default")
        user = update.effective_user.first_name
        
        # Индикатор печати
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # Генерация ответа
        response = await ChatManager.get_response(text, user, mode)
        await update.message.reply_text(response)

    elif intent == 'search':
        await _do_play(chat_id, query, context)
        
    elif intent == 'radio':
        # --- НОВАЯ ЛОГИКА ДЛЯ РАДИО ---
        await update.message.reply_text(f"📻 Ловлю волну: {query}...")
        
        # Здесь нужно вызвать твою функцию запуска радио.
        # Обычно это работает через подмену аргументов контекста:
        context.args = [query] # Имитируем, будто юзер написал "/radio query"
        
        # Вызываем функцию, которая у тебя привязана к команде /radio
        await radio_command(update, context)

# --- КОМАНДЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎧 Aurora v3.0. Жду команд!")

async def radio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else "top hits"
    await _do_radio(update.effective_chat.id, query, context)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверка админа
    settings = get_settings()
    if update.effective_user.id not in settings.ADMIN_ID_LIST:
        return

    keyboard = []
    for mode in PERSONAS.keys():
        keyboard.append([InlineKeyboardButton(f"🎭 {mode.upper()}", callback_data=f"set_mode|{mode}")])
    keyboard.append([InlineKeyboardButton("❌ Закрыть", callback_data="close_admin")])
    await update.message.reply_text("⚙️ Выбор личности ИИ:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "close_admin":
        await query.delete_message()
    elif query.data.startswith("set_mode|"):
        mode = query.data.split("|")[1]
        # СОХРАНЯЕМ В CONTEXT (Вот это работает!)
        context.chat_data["mode"] = mode
        await context.bot.send_message(update.effective_chat.id, f"✅ Режим изменен на: {mode}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.chat_data.get("mode", "default")
    await update.message.reply_text(f"📊 Info:\nMode: {mode}\nAI: Active")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.application.radio_manager.stop(update.effective_chat.id)
    await update.message.reply_text("🛑 Stop.")

def setup_handlers(app, radio, settings, downloader, spotify_service):
    app.downloader = downloader
    app.radio_manager = radio
    app.spotify_service = spotify_service
    app.settings = settings
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("radio", radio_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_callback))
