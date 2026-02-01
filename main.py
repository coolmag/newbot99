import logging
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from youtube import YouTubeDownloader
from cache_service import CacheService
from ai_manager import AIManager
from radio import RadioManager
from spotify import SpotifyService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

settings = get_settings()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cache_service = CacheService(settings.CACHE_DB_PATH)
downloader = YouTubeDownloader(settings, cache_service)
spotify_service = SpotifyService(settings, downloader)
ai_manager = AIManager()

# Создаем папку статики, если нет
Path("static").mkdir(exist_ok=True)

# Монтируем статику, но index.html будем отдавать отдельно
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup_event():
    await cache_service.initialize()
    from telegram.ext import Application
    from handlers import setup_handlers
    
    application = Application.builder().token(settings.BOT_TOKEN).build()
    radio_manager = RadioManager(application.bot, settings, downloader)
    setup_handlers(application, radio_manager, settings, downloader, spotify_service=spotify_service)
    
    await application.initialize()
    await application.start()
    
    try:
        webhook_url = f"{settings.BASE_URL}/telegram"
        await application.bot.set_webhook(webhook_url)
    except Exception as e:
        logger.warning(f"Webhook setup failed: {e}")

    app.state.application = application
    app.state.radio_manager = radio_manager

@app.get("/api/player/playlist")
async def api_playlist(query: str):
    if not query: return {"playlist": []}
    tracks = await downloader.search(query, limit=20)
    for t in tracks:
        await cache_service.set(f"meta:{t.identifier}", t, ttl=3600)
    
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
    if not prompt: return {"playlist": []}
    analysis = await ai_manager.analyze_message(prompt)
    search_query = analysis.get("query", prompt) if analysis else prompt
    return await api_playlist(search_query)

@app.get("/stream/{video_id}")
async def stream_track(video_id: str):
    final_path = settings.DOWNLOADS_DIR / f"{video_id}.mp3"
    if final_path.exists() and final_path.stat().st_size > 10000:
        return FileResponse(final_path, media_type="audio/mpeg")

    track_info = await cache_service.get(f"meta:{video_id}")
    logger.info(f"🌐 Web Player: Downloading {video_id}...")
    result = await downloader.download(video_id, track_info=track_info)
    
    if result.success and result.file_path:
        return FileResponse(result.file_path, media_type="audio/mpeg")
    return JSONResponse(status_code=404, content={"error": "Download failed"})

@app.post("/telegram")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        from telegram import Update
        application = app.state.application
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return {"status": "ok"}

# 🔥 ФИКС КЭША: Принудительно отдаем index.html без кэширования
@app.get("/")
async def root():
    response = FileResponse("static/index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
