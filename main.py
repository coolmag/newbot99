import logging
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings # Changed import to use get_settings
from youtube import YouTubeDownloader
from cache_service import CacheService
from ai_manager import AIManager # Нужен для AI DJ
from radio import RadioManager
from spotify import SpotifyService # Import spotify

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Settings
settings = get_settings() # Moved here to be accessible globally

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services
cache_service = CacheService(settings.CACHE_DB_PATH) # Initialize with path
downloader = YouTubeDownloader(settings, cache_service)
spotify_service = SpotifyService(settings, downloader) # Initialize spotify
ai_manager = AIManager()

# Переменные приложения
# bot = None # No longer needed globally if application handles it
# radio_manager = None # No longer needed globally if application handles it

# Статика
Path("static").mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static") # Changed to serve index.html directly from root

@app.on_event("startup")
async def startup_event():
    # global bot, radio_manager # Removed global if application is used
    from telegram.ext import Application
    from handlers import setup_handlers
    
    application = Application.builder().token(settings.BOT_TOKEN).build() # Use BOT_TOKEN from settings
    # bot = application.bot # Not needed globally
    radio_manager = RadioManager(application.bot, settings, downloader)
    setup_handlers(application, radio_manager, settings, downloader, spotify_service=spotify_service) # Pass the real spotify_service
    
    await application.initialize()
    await application.start()
    
    # Webhook
    try:
        webhook_url = f"{settings.BASE_URL}/telegram"
        await application.bot.set_webhook(webhook_url)
    except Exception as e:
        logger.warning(f"Webhook setup failed (local test?): {e}")

    app.state.application = application # Store application in app.state for webhook
    app.state.radio_manager = radio_manager # Store radio_manager in app.state for access

# --- НОВЫЕ API ДЛЯ ТВОЕГО ПЛЕЕРА ---

@app.get("/api/player/playlist")
async def api_playlist(query: str):
    """
    Поиск музыки для плеера.
    Возвращает JSON в формате, который ждет твой скрипт: { playlist: [...] }
    """
    if not query: return {"playlist": []}
    
    tracks = await downloader.search(query, limit=20)
    
    return {
        "playlist": [
            {
                "identifier": t.identifier,
                "title": t.title,
                "artist": getattr(t, 'uploader', getattr(t, 'artist', 'Unknown')),
                "duration": t.duration,
                "cover": t.thumbnail_url
            }
            for t in tracks
        ]
    }

@app.get("/api/ai/dj")
async def api_ai_dj(prompt: str):
    """
    AI DJ: Генерирует поисковый запрос из промпта и возвращает плейлист.
    """
    if not prompt: return {"playlist": []}
    
    # Спрашиваем AI, что имел в виду пользователь
    analysis = await ai_manager.analyze_message(prompt)
    search_query = analysis.get("query", prompt) if analysis else prompt
    
    # Ищем музыку по сгенерированному запросу
    return await api_playlist(search_query)

@app.get("/stream/{video_id}")
async def stream_track(video_id: str):
    """
    Стриминг трека.
    Формат URL: /stream/VIDEO_ID
    """
    final_path = settings.DOWNLOADS_DIR / f"{video_id}.mp3"
    
    # 1. Если файл есть - стримим его
    if final_path.exists() and final_path.stat().st_size > 10000:
        return FileResponse(final_path, media_type="audio/mpeg")

    # 2. Если нет - качаем
    # (В реальном продакшене тут лучше возвращать 202 Accepted или ждать)
    logger.info(f"🌐 Web Player: Downloading {video_id}...")
    result = await downloader.download(video_id)
    
    if result.success and result.file_path:
        return FileResponse(result.file_path, media_type="audio/mpeg")
    
    return JSONResponse(status_code=404, content={"error": "Download failed"})

# Webhook Handler
@app.post("/telegram")
async def telegram_webhook(request: Request):
    logger.info("Received a request on the webhook.") # Added for debugging
    try:
        data = await request.json()
        from telegram import Update
        application = app.state.application
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return {"status": "ok"}

# Root
@app.get("/")
async def root():
    if Path("static/index.html").exists():
        return FileResponse("static/index.html")
    return {"status": "Aurora Bot Active"}