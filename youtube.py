import asyncio
import logging
from pathlib import Path
from typing import List, Optional

import yt_dlp
from ytmusicapi import YTMusic
from config import Settings
from models import DownloadResult, TrackInfo
from cache_service import CacheService
from proxy_manager import ProxyManager

logger = logging.getLogger(__name__)

class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): logger.error(msg)

class YouTubeDownloader:
    def __init__(self, settings: Settings, cache_service: CacheService, proxy_manager: ProxyManager):
        self._settings = settings
        self._cache = cache_service
        self._proxy_manager = proxy_manager
        self._settings.DOWNLOADS_DIR.mkdir(exist_ok=True)
        self.semaphore = asyncio.Semaphore(3)
        self.ytmusic = YTMusic() 

    async def search(self, query: str, limit: int = 10, **kwargs) -> List[TrackInfo]:
        if kwargs.get('decade'):
            query = f"{query} {kwargs['decade']}"
        if not query or not query.strip(): return []
            
        logger.info(f"🔎 Search: {query}")
        loop = asyncio.get_running_loop()
        
        try:
            return await self._search_internal(query, "songs", limit, loop)
        except: pass

        try:
            return await self._search_internal(query, "videos", limit, loop)
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    async def _search_internal(self, query, filter_type, limit, loop):
        search_results = await loop.run_in_executor(None, lambda: self.ytmusic.search(query, filter=filter_type, limit=limit))
        valid_tracks = []
        
        for item in search_results:
            video_id = item.get('videoId')
            if not video_id: continue
            
            artists = ", ".join([a['name'] for a in item.get('artists', [])])
            title = item.get('title')
            
            duration = 0
            try:
                parts = item.get('duration', '0:00').split(':')
                if len(parts) == 2: duration = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3: duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except: pass
            
            if duration < 30 or duration > 1200: continue

            track = TrackInfo(
                identifier=video_id, title=title, uploader=artists,
                duration=duration, thumbnail_url=item.get('thumbnails', [{}])[-1].get('url'),
                source="ytmusic"
            )
            valid_tracks.append(track)
        return valid_tracks

    async def get_track_info(self, video_id: str) -> Optional[TrackInfo]:
        try:
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, lambda: self.ytmusic.get_song(video_id))
            video_details = info.get('videoDetails', {})
            return TrackInfo(
                identifier=video_details.get('videoId', video_id),
                title=video_details.get('title', 'Unknown'),
                uploader=video_details.get('author', 'Unknown'),
                duration=int(video_details.get('lengthSeconds', 0)),
                thumbnail_url=video_details.get('thumbnail', {}).get('thumbnails', [])[-1]['url'] if video_details.get('thumbnail') else None
            )
        except: return None

    async def download(self, video_id: str, track_info: Optional[TrackInfo] = None) -> DownloadResult:
        final_path = self._settings.DOWNLOADS_DIR / f"{video_id}.mp3"
        if final_path.exists() and final_path.stat().st_size > 10000:
            return DownloadResult(success=True, file_path=final_path, track_info=track_info)

        if not track_info:
            track_info = await self.get_track_info(video_id)

        async with self.semaphore:
            query = f"{track_info.uploader} - {track_info.title}" if track_info else video_id
            return await self._download_sc(query, final_path, track_info)

    def _progress_hook(self, d): pass

    async def _download_sc(self, query: str, target_path: Path, track_info: TrackInfo) -> DownloadResult:
        temp_path = str(target_path).replace(".mp3", "_temp")
        
        # 🔥 PROXY INJECTION
        proxy_opts = self._proxy_manager.get_yt_dlp_proxy_opts()
        current_proxy = proxy_opts.get('http_proxy')
        
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_path,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'logger': QuietLogger(),
            'progress_hooks': [self._progress_hook],
            'noplaylist': True,
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}],
            'nocheckcertificate': True,
        }
        
        if current_proxy:
            opts['proxy'] = current_proxy

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._run_yt_dlp(opts, f"scsearch1:{query}"))
            
            paths = [Path(temp_path + ".mp3"), Path(temp_path)]
            for p in paths:
                if p.exists() and p.stat().st_size > 10000:
                    if p != target_path:
                        if target_path.exists(): target_path.unlink()
                        p.rename(target_path)
                    return DownloadResult(success=True, file_path=target_path, track_info=track_info)
            
            if current_proxy:
                self._proxy_manager.report_dead_proxy(current_proxy)
            return DownloadResult(success=False, error_message="Not found")
            
        except Exception as e:
            logger.error(f"DL Error: {e}")
            if current_proxy:
                self._proxy_manager.report_dead_proxy(current_proxy)
            return DownloadResult(success=False, error_message=str(e))

    def _run_yt_dlp(self, opts, url):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
