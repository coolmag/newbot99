from __future__ import annotations
import logging
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters
)

from radio import RadioManager
from config import get_settings
from chat_service import ChatManager
from nlp import analyze_message

logger = logging.getLogger("handlers")

async def _do_radio(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE):
    search_query = query if query and query not in ['query', 'None'] else "top hits 2025"
    await context.bot.send_message(chat_id, f"📡 Радио: *{search_query}*", parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(context.application.radio_manager.start(chat_id, search_query))

async def _do_play(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE):
    msg = await context.bot.send_message(chat_id, f"🔎 Ищу метаданные: {query}...", parse_mode=ParseMode.MARKDOWN)
    
    # 1. Ищем инфо на YTMusic
    tracks = await context.application.downloader.search(query, limit=1)
    
    if not tracks:
        await msg.edit_text("❌ Не найдено даже описание.")
        return

    track = tracks[0]
    await msg.edit_text(f"🔍 Ищу аудио на SoundCloud: {track.title}...")
    
    # 2. Пробуем скачать с SC
    dl_res = await context.application.downloader.download(track.identifier, track)
    
    await msg.delete()
    
    if dl_res.success:
        with open(dl_res.file_path, 'rb') as f:
            await context.bot.send_audio(chat_id=chat_id, audio=f, title=dl_res.track_info.title, performer=dl_res.track_info.uploader)
        # Удаляем после отправки (экономия места)
        try: dl_res.file_path.unlink()
        except: pass
    else:
        # !!! ВАЖНО: Говорим юзеру правду
        await context.bot.send_message(chat_id, f"❌ Трек *{track.title}* найден в базе, но аудио нет на SoundCloud.\nПопробуйте другой трек.", parse_mode=ParseMode.MARKDOWN)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text: return

    # Простая маршрутизация
    if text.startswith('/'): return # Игнор команд

    analysis = await analyze_message(text)
    intent = analysis['intent']
    query = analysis['query']
    
    if intent == 'chat':
        mode = context.chat_data.get("mode", "default")
        user = update.effective_user.first_name
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        response = await ChatManager.get_response(text, user, mode)
        await update.message.reply_text(response)

    elif intent == 'search':
        await _do_play(chat_id, query, context)
        
    elif intent == 'radio':
        await update.message.reply_text(f"📻 Включаю: {query}...")
        context.args = [query]
        await radio_command(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎧 Aurora v3.3. Готова к эфиру!")

async def radio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else "top hits"
    await _do_radio(update.effective_chat.id, query, context)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.application.radio_manager.stop(update.effective_chat.id)
    await update.message.reply_text("🛑 Эфир остановлен.")

def setup_handlers(app, radio, settings, downloader, spotify_service):
    app.downloader = downloader
    app.radio_manager = radio
    app.spotify_service = spotify_service
    app.settings = settings
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("radio", radio_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))