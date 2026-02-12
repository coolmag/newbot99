import logging
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import get_settings
from youtube import YouTubeDownloader
from cache_service import CacheService
from ai_manager import AIManager
from radio import RadioManager


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
ai_manager = AIManager()

Path("static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup_event():
    """Starts the bot in polling mode for GitHub Actions deployment."""
    await cache_service.initialize()
    from telegram.ext import Application
    from handlers import setup_handlers

    logger.info("Starting bot in polling mode for GitHub Actions deployment.")

    # Build the application with the real token. No proxy, no base_url.
    application = Application.builder().token(settings.BOT_TOKEN).build()

    # Setup other components
    radio_manager = RadioManager(application.bot, settings, downloader)
    setup_handlers(application, radio_manager, settings, downloader)
    
    # Initialize the application
    await application.initialize()
    
    # Start polling as a background task.
    # run_polling() is blocking, but loop.create_task() runs it in the background
    # so it doesn't block the Uvicorn server startup.
    loop = asyncio.get_event_loop()
    loop.create_task(application.run_polling())
    
    logger.info("Bot has been initialized and polling is running in the background.")

    # Store application and radio_manager in app state if needed by web routes
    app.state.application = application
    app.state.radio_manager = radio_manager

class AIRequest(BaseModel):
    prompt: str

@app.post("/api/ai/chat")
async def api_ai_chat(request: AIRequest):
    resp = await ai_manager.get_chat_response(request.prompt)
    return {"response": resp}

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
                "artist": getattr(t, 'uploader', 'Unknown'),
                "duration": t.duration,
                "cover": t.thumbnail_url
            }
            for t in tracks
        ]
    }

@app.get("/stream/{video_id}")
async def stream_track(video_id: str):
    final_path = settings.DOWNLOADS_DIR / f"{video_id}.mp3"
    
    if final_path.exists() and final_path.stat().st_size > 10000:
        return FileResponse(final_path, media_type="audio/mpeg")

    track_info = await cache_service.get(f"meta:{video_id}")
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

@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>System Error</h1>", status_code=404)