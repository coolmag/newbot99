import logging
from contextlib import asynccontextmanager
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
from proxy_manager import ProxyManager
from logging_setup import setup_logging

setup_logging()
logger = logging.getLogger("main")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Start Services
    cache_service = CacheService(settings.CACHE_DB_PATH)
    await cache_service.initialize()
    
    proxy_manager = ProxyManager(settings.BASE_DIR)
    ai_manager = AIManager()
    
    downloader = YouTubeDownloader(settings, cache_service, proxy_manager)
    spotify_service = SpotifyService(settings, downloader)
    
    # 2. Start Bot
    from telegram.ext import Application
    from handlers import setup_handlers
    
    bot_app = Application.builder().token(settings.BOT_TOKEN).build()
    
    # Инициализируем зависимости
    radio_manager = RadioManager(bot_app.bot, settings, downloader)
    
    # Внедряем AI в приложение бота, чтобы хендлеры видели его
    bot_app.ai_manager = ai_manager
    
    setup_handlers(bot_app, radio_manager, settings, downloader, spotify_service)
    
    await bot_app.initialize()
    await bot_app.start()
    
    try:
        webhook_url = f"{settings.BASE_URL}/telegram"
        await bot_app.bot.set_webhook(webhook_url)
        logger.info(f"🔗 Webhook: {webhook_url}")
    except Exception as e:
        logger.warning(f"Webhook failed: {e}")

    # Inject into App State for API routes
    app.state.application = bot_app
    app.state.radio_manager = radio_manager
    app.state.downloader = downloader
    app.state.ai_manager = ai_manager
    app.state.cache = cache_service
    
    yield
    
    logger.info("🛑 Shutting down...")
    await bot_app.stop()
    await bot_app.shutdown()
    await cache_service.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path("static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/api/player/playlist")
async def api_playlist(query: str):
    if not query: return {"playlist": []}
    tracks = await app.state.downloader.search(query, limit=20)
    for t in tracks:
        await app.state.cache.set(f"meta:{t.identifier}", t, ttl=3600)
    
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
    analysis = await app.state.ai_manager.analyze_message(prompt)
    search_query = analysis.get("query", prompt) if analysis else prompt
    return await api_playlist(search_query)

@app.get("/stream/{video_id}")
async def stream_track(video_id: str):
    final_path = settings.DOWNLOADS_DIR / f"{video_id}.mp3"
    
    if final_path.exists() and final_path.stat().st_size > 10000:
        return FileResponse(final_path, media_type="audio/mpeg")

    track_info = await app.state.cache.get(f"meta:{video_id}")
    result = await app.state.downloader.download(video_id, track_info=track_info)
    
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

@app.get("/")
async def root():
    response = FileResponse("static/index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
