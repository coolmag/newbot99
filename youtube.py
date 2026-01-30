import asyncio
import logging
import random
import inspect
from pathlib import Path
from typing import List, Optional

import yt_dlp
from ytmusicapi import YTMusic
from config import Settings
from models import DownloadResult, TrackInfo
from cache_service import CacheService
from proxy_service import ProxyManager

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    """
    🎵 Hybrid Edition (v47 - Instant Fallback).
    Priority 1: YTMusic + V2Ray (Timeout 15s).
    Priority 2: SoundCloud (Instant Fallback).
    """
    
    def __init__(self, settings: Settings, cache_service: CacheService):
        self._settings = settings
        self._cache = cache_service
        self._settings.DOWNLOADS_DIR.mkdir(exist_ok=True)
        self.semaphore = asyncio.Semaphore(1)
        self.ytmusic = YTMusic() 
        proxies_file = Path("hiddify_compatible_v2ray_proxies.txt")
        self._proxy_manager = ProxyManager(proxies_file)

    async def search(self, query: str, limit: int = 10, **kwargs) -> List[TrackInfo]:
        if kwargs.get('decade'):
            query = f"{query} {kwargs['decade']}"
        if not query or not query.strip(): return []
            
        logger.info(f"🔎 YTMusic Search: {query}")
        
        loop = asyncio.get_running_loop()
        try:
            search_results = await loop.run_in_executor(None, lambda: self.ytmusic.search(query, filter="songs", limit=limit))
            
            sig = inspect.signature(TrackInfo)
            has_uploader = 'uploader' in sig.parameters
            
            results = []
            for item in search_results:
                video_id = item.get('videoId')
                if not video_id: continue
                
                artists = ", ".join([a['name'] for a in item.get('artists', [])])
                duration_text = item.get('duration', '0:00')
                try:
                    parts = duration_text.split(':')
                    duration = int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else int(parts[0])
                except: duration = 0
                
                if duration > 900: continue

                track_args = {
                    'identifier': video_id,
                    'title': item.get('title'),
                    'duration': duration,
                    'thumbnail_url': item.get('thumbnails', [{}])[-1].get('url'),
                    'source': "ytmusic"
                }
                if has_uploader: track_args['uploader'] = artists
                else: track_args['artist'] = artists
                
                results.append(TrackInfo(**track_args))
            
            logger.info(f"✅ Found {len(results)} tracks on YTMusic")
            return results

        except Exception as e:
            logger.error(f"❌ YTMusic Search error: {e}")
            return []

    async def download(self, video_id: str, track_info: Optional[TrackInfo] = None) -> DownloadResult:
        final_path = self._settings.DOWNLOADS_DIR / f"{video_id}.mp3"
        if final_path.exists() and final_path.stat().st_size > 10000:
            logger.info(f"✅ Cache hit for {video_id}")
            return DownloadResult(success=True, file_path=final_path, track_info=track_info)

        # 1. Пробуем запустить прокси (быстро, 10 сек)
        # Если прокси рабочие - ок. Если нет - сразу идем дальше.
        proxy_started = False
        try:
            proxy_started = await self._proxy_manager.start_proxy(timeout=10)
        except Exception:
            pass

        if proxy_started:
            try:
                async with self.semaphore:
                    logger.info(f"🎧 Downloading {video_id} via V2Ray...")
                    res = await self._download_yt_smart(video_id, final_path, track_info)
                    if res.success: return res
            finally:
                self._proxy_manager.stop_proxy()
        else:
            logger.warning("🚫 Proxy failed to start. Switching to Fallback.")

        # 2. Фолбэк на SoundCloud (Работает всегда)
        if track_info:
            # Формируем точный запрос: Исполнитель + Название
            # Получаем имя поля артиста динамически
            artist = getattr(track_info, 'uploader', getattr(track_info, 'artist', ''))
            sc_query = f"{artist} - {track_info.title}"
            
            logger.info(f"☁️ Fallback: Downloading '{sc_query}' from SoundCloud...")
            return await self._download_soundcloud_fallback(sc_query, final_path, track_info)
            
        return DownloadResult(success=False, error_message="All download methods failed")

    async def _download_yt_smart(self, video_id: str, target_path: Path, track_info: TrackInfo) -> DownloadResult:
        temp_path = str(target_path).replace(".mp3", "_temp")
        opts = {
            'format': 'bestaudio/best', 'outtmpl': temp_path, 'quiet': True, 'nocheckcertificate': True,
            'proxy': self._proxy_manager.active_proxy_url,
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]
        }
        
        # Пробуем Android клиент (самый быстрый с прокси)
        opts['extractor_args'] = {'youtube': {'player_client': ['android']}}
        
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._run_yt_dlp(opts, f"https://music.youtube.com/watch?v={video_id}"))
            
            paths = [Path(temp_path + ".mp3"), Path(temp_path)]
            for p in paths:
                if p.exists() and p.stat().st_size > 10000:
                    if p != target_path: 
                        if target_path.exists(): target_path.unlink()
                        p.rename(target_path)
                    return DownloadResult(success=True, file_path=target_path, track_info=track_info)
        except Exception: pass
        return DownloadResult(success=False)

    async def _download_soundcloud_fallback(self, query: str, target_path: Path, track_info: TrackInfo) -> DownloadResult:
        """Скачивает трек с SC. Прокси НЕ используются."""
        temp_path = str(target_path).replace(".mp3", "_sc_temp")
        
        opts = {
            'format': 'bestaudio/best', 'outtmpl': temp_path, 'quiet': True, 'noplaylist': True,
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]
        }
        
        try:
            loop = asyncio.get_running_loop()
            # scsearch1: ищет 1 самый релевантный трек
            await loop.run_in_executor(None, lambda: self._run_yt_dlp(opts, f"scsearch1:{query}"))
            
            paths = [Path(temp_path + ".mp3"), Path(temp_path)]
            for p in paths:
                if p.exists() and p.stat().st_size > 10000:
                    if p != target_path:
                        if target_path.exists(): target_path.unlink()
                        p.rename(target_path)
                    logger.info(f"✅ Success via SoundCloud: {query}")
                    return DownloadResult(success=True, file_path=target_path, track_info=track_info)
        except Exception as e:
            logger.error(f"SoundCloud fallback failed: {e}")
            
        return DownloadResult(success=False, error_message="SC Fallback failed")

    def _run_yt_dlp(self, opts, url):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
