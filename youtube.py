import asyncio
import logging
from pathlib import Path
from typing import List, Optional

import yt_dlp
from ytmusicapi import YTMusic
from config import Settings, get_settings
from models import DownloadResult, TrackInfo
from cache_service import CacheService

logger = logging.getLogger(__name__)
settings = get_settings()

class YouTubeDownloader:
    """
    ⚡ Metadata: YTMusic | Audio: SoundCloud ONLY.
    """
    
    def __init__(self, settings: Settings, cache_service: CacheService):
        self._settings = settings
        self._cache = cache_service
        self._settings.DOWNLOADS_DIR.mkdir(exist_ok=True)
        # SoundCloud не банит, можно 3 потока
        self.semaphore = asyncio.Semaphore(3)
        self.ytmusic = YTMusic() 

    # 1. ИЩЕМ НА YOUTUBE (МЕТАДАННЫЕ)
    async def search(self, query: str, limit: int = 10, **kwargs) -> List[TrackInfo]:
        if kwargs.get('decade'): query = f"{query} {kwargs['decade']}"
        if not query or not query.strip(): return []

        logger.info(f"🔎 YT Metadata Search: {query}")
        loop = asyncio.get_running_loop()

        try:
            # Безопасный поиск через API (не банится)
            search_results = await loop.run_in_executor(None, lambda: self.ytmusic.search(query, filter="songs", limit=limit))
            
            results = []
            for item in search_results:
                video_id = item.get('videoId')
                if not video_id: continue

                artists = ", ".join([a['name'] for a in item.get('artists', [])])
                
                duration = 0
                try:
                    d_str = item.get('duration', '0:00')
                    parts = d_str.split(':')
                    if len(parts) == 3: duration = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                    elif len(parts) == 2: duration = int(parts[0])*60 + int(parts[1])
                    else: duration = int(parts[0])
                except: pass
                
                if duration > 900 or duration == 0: continue

                track = TrackInfo(
                    identifier=video_id, 
                    title=item.get('title'), 
                    uploader=artists, 
                    duration=duration, 
                    thumbnail_url=item.get('thumbnails', [{}])[-1].get('url'), 
                    source="ytmusic"
                )
                results.append(track)
            return results
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    async def get_track_info(self, video_id: str) -> Optional[TrackInfo]:
        try:
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, lambda: self.ytmusic.get_song(video_id))
            video_details = info.get('videoDetails', {})
            if not video_details: return None
            
            thumbnails = video_details.get('thumbnail', {}).get('thumbnails', [])
            thumb_url = thumbnails[-1]['url'] if thumbnails else None

            return TrackInfo(
                identifier=video_details.get('videoId', video_id),
                title=video_details.get('title', 'Unknown'),
                uploader=video_details.get('author', 'Unknown'),
                duration=int(video_details.get('lengthSeconds', 0)),
                thumbnail_url=thumb_url,
                source="ytmusic"
            )
        except: return None

    # 2. КАЧАЕМ С SOUNDCLOUD (АУДИО)
    async def download(self, video_id: str, track_info: Optional[TrackInfo] = None) -> DownloadResult:
        final_path = self._settings.DOWNLOADS_DIR / f"{video_id}.mp3"
        
        # Кэш
        if final_path.exists() and final_path.stat().st_size > 50000:
            return DownloadResult(success=True, file_path=final_path, track_info=track_info)

        if not track_info:
            track_info = await self.get_track_info(video_id)
            
        if not track_info:
            return DownloadResult(success=False, error_message="Metadata failed")

        async with self.semaphore:
            query = f"{track_info.uploader} - {track_info.title}"
            logger.info(f"☁️ SC Attempt: {query}")
            return await self._download_sc_only(query, final_path, track_info)

    async def _download_sc_only(self, query: str, target_path: Path, track_info: Optional[TrackInfo]) -> DownloadResult:
        temp_path = str(target_path).replace(".mp3", "_temp")
        
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_path,
            'quiet': True,
            'noprogress': True,
            'noplaylist': True,
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}],
        }
        
        try:
            loop = asyncio.get_running_loop()
            # scsearch1 = найти первый результат
            await loop.run_in_executor(None, lambda: self._run_yt_dlp(opts, f"scsearch1:{query}"))
            
            paths = [Path(temp_path + ".mp3"), Path(temp_path)]
            for p in paths:
                if p.exists() and p.stat().st_size > 10000:
                    if p != target_path:
                        if target_path.exists(): target_path.unlink()
                        p.rename(target_path)
                    return DownloadResult(success=True, file_path=target_path, track_info=track_info)
            
            logger.warning(f"❌ SC Not Found: {query}")
            return DownloadResult(success=False, error_message="Audio not found on SoundCloud")
            
        except Exception as e:
            return DownloadResult(success=False, error_message=str(e))

    def _run_yt_dlp(self, opts, url):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
