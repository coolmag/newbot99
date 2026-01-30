import asyncio
import logging
from pathlib import Path
from typing import List, Optional

import yt_dlp
from ytmusicapi import YTMusic
from config import get_settings, Settings
from models import DownloadResult, TrackInfo
from cache_service import CacheService

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    """
    ⚡ Speed Edition (v48).
    Removed dead Proxies.
    Search: YTMusic (Best metadata).
    Download: SoundCloud (Immediate search & download by title).
    """
    
    def __init__(self, settings: Settings, cache_service: CacheService):
        self._settings = settings
        self._cache = cache_service
        self._settings.DOWNLOADS_DIR.mkdir(exist_ok=True)
        self.semaphore = asyncio.Semaphore(3) # Качаем в 3 потока
        self.ytmusic = YTMusic() 

    async def search(self, query: str, limit: int = 10, **kwargs) -> List[TrackInfo]:
        if kwargs.get('decade'):
            query = f"{query} {kwargs['decade']}"
        if not query or not query.strip(): return []
            
        logger.info(f"🔎 YTMusic Search: {query}")
        
        loop = asyncio.get_running_loop()
        try:
            search_results = await loop.run_in_executor(None, lambda: self.ytmusic.search(query, filter="songs", limit=limit))
            
            results = []
            for item in search_results:
                video_id = item.get('videoId')
                if not video_id: continue
                
                artists = ", ".join([a['name'] for a in item.get('artists', [])])
                title = item.get('title')
                
                # Парсинг длительности
                duration = 0
                try:
                    parts = item.get('duration', '0:00').split(':')
                    if len(parts) == 2:
                        duration = int(parts[0]) * 60 + int(parts[1])
                    else:
                        duration = int(parts[0])
                except: pass
                
                if duration > 900: continue # Не качаем миксы > 15 мин

                track = TrackInfo(
                    identifier=video_id,
                    title=title,
                    uploader=artists, # Поле называется uploader в твоем models.py
                    duration=duration,
                    thumbnail_url=item.get('thumbnails', [{}])[-1].get('url'),
                    source="ytmusic"
                )
                results.append(track)
            
            return results
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    async def download(self, video_id: str, track_info: Optional[TrackInfo] = None) -> DownloadResult:
        # Имя файла - ID с ютуба (чтобы не было дублей)
        final_path = self._settings.DOWNLOADS_DIR / f"{video_id}.mp3"
        
        if final_path.exists() and final_path.stat().st_size > 10000:
            logger.info(f"✅ Cache hit: {track_info.title if track_info else video_id}")
            return DownloadResult(success=True, file_path=final_path, track_info=track_info)

        async with self.semaphore:
            # Формируем запрос для SoundCloud: "Artist - Title"
            query = video_id
            if track_info:
                query = f"{track_info.uploader} - {track_info.title}"
            
            logger.info(f"☁️ Fast Download (SC): {query}")
            return await self._download_sc(query, final_path, track_info)

    async def _download_sc(self, query: str, target_path: Path, track_info: TrackInfo) -> DownloadResult:
        temp_path = str(target_path).replace(".mp3", "_temp")
        
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_path,
            'quiet': True,
            'noplaylist': True,
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}],
        }
        
        try:
            loop = asyncio.get_running_loop()
            # scsearch1: ищет 1 самый похожий трек на SoundCloud
            await loop.run_in_executor(None, lambda: self._run_yt_dlp(opts, f"scsearch1:{query}"))
            
            # Проверяем результат (yt-dlp мог добавить .mp3)
            paths = [Path(temp_path + ".mp3"), Path(temp_path)]
            for p in paths:
                if p.exists() and p.stat().st_size > 10000:
                    if p != target_path:
                        if target_path.exists(): target_path.unlink()
                        p.rename(target_path)
                    
                    logger.info(f"✅ Downloaded: {query}")
                    return DownloadResult(success=True, file_path=target_path, track_info=track_info)
            
            logger.warning(f"SC search found nothing for: {query}")
            return DownloadResult(success=False, error_message="Not found on SoundCloud")
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return DownloadResult(success=False, error_message=str(e))

    def _run_yt_dlp(self, opts, url):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])