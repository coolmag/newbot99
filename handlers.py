from __future__ import annotations
import logging
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)

from ai_personas import PERSONAS
from ai_manager import AIManager

logger = logging.getLogger("handlers")

async def _do_radio(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE):
    if not query or query in ['query', 'None', 'null']:
        query = "top hits 2026"
    
    await context.bot.send_message(chat_id, f"📡 Радио: *{query}*", parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(context.application.radio_manager.start(chat_id, query))

async def _do_play(chat_id: int, query: str, context: ContextTypes.DEFAULT_TYPE):
    msg = await context.bot.send_message(chat_id, f"🔎 Поиск: {query}...", parse_mode=ParseMode.MARKDOWN)
    tracks = await context.application.downloader.search(query, limit=1)
    
    if not tracks:
        await msg.edit_text("❌ Ничего не найдено.")
        return

    await msg.delete()
    dl_res = await context.application.downloader.download(tracks[0].identifier, tracks[0])
    
    if dl_res.success:
        with open(dl_res.file_path, 'rb') as f:
            await context.bot.send_audio(chat_id=chat_id, audio=f, title=dl_res.track_info.title, performer=dl_res.track_info.artist)
    else:
        await context.bot.send_message(chat_id, "❌ Ошибка загрузки.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text
    chat_id = update.effective_chat.id
    if not text: return

    # 1. Spotify
    if "open.spotify.com/track" in text:
        await context.bot.send_message(chat_id, "🎵 Spotify Link detected...")
        dl = await context.application.spotify_service.download_from_url(text)
        if dl.success:
            with open(dl.file_path, 'rb') as f:
                await context.bot.send_audio(chat_id=chat_id, audio=f, title=dl.track_info.title, performer=dl.track_info.artist)
        return

    # 2. AI Analysis
    ai: AIManager = context.application.ai_manager
    
    intent = "chat"
    query = text
    
    try:
        analysis = await ai.analyze_message(text)
        if analysis:
            intent = analysis.get("intent", "chat")
            query = analysis.get("query", text)
    except Exception as e:
        logger.error(f"NLP Error: {e}")

    # 3. Routing
    if intent == 'radio':
        await _do_radio(chat_id, query, context)
    elif intent == 'search':
        await _do_play(chat_id, query, context)
    else:
        mode = context.chat_data.get("mode", "default")
        user = update.effective_user.first_name
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        response = await ai.get_chat_response(text, user, PERSONAS.get(mode, ""))
        await update.message.reply_text(response)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎧 Aurora v3.0 (2026). Ready.")

async def radio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else "top hits"
    await _do_radio(update.effective_chat.id, query, context)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in context.application.settings.ADMIN_ID_LIST: return
    keyboard = [[InlineKeyboardButton(f"🎭 {m.upper()}", callback_data=f"set_mode|{m}")] for m in PERSONAS.keys()]
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="close_admin")])
    await update.message.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "close_admin":
        await query.delete_message()
    elif query.data.startswith("set_mode|"):
        mode = query.data.split("|")[1]
        context.chat_data["mode"] = mode
        await context.bot.send_message(update.effective_chat.id, f"✅ Mode: {mode}")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.application.radio_manager.stop(update.effective_chat.id)
    await update.message.reply_text("🛑 Stopped.")

def setup_handlers(app, radio, settings, downloader, spotify_service):
    app.downloader = downloader
    app.radio_manager = radio
    app.spotify_service = spotify_service
    app.settings = settings
    # ВАЖНО: AI менеджер уже есть в app.ai_manager после инициализации в main.py
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("radio", radio_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_callback))
