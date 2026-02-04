import asyncio
import logging
import random
import os
import time
from typing import List, Optional, Dict, Set
from dataclasses import dataclass, field
from telegram import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.error import BadRequest, RetryAfter, Forbidden
from config import Settings, RADIO_PRESETS
from models import TrackInfo, DownloadResult
from youtube import YouTubeDownloader
import json
from pathlib import Path

# Load MUSIC_CATALOG
with open(Path(__file__).parent / "genres.json", "r", encoding="utf-8") as f:
    MUSIC_CATALOG = json.load(f)

logger = logging.getLogger("radio")

def format_duration(seconds: int) -> str:
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d}"

def get_now_playing_message(track: TrackInfo, genre_name: str) -> str:
    icon = random.choice(["🎧", "🎵", "🎶", "📻", "💿"])
    title = track.title[:40].strip()
    artist = track.uploader[:30].strip()
    return f"{icon} *{title}*\n👤 {artist}\n⏱ {format_duration(track.duration)} | 📻 _{genre_name}_"

 @dataclass
class RadioSession:
    chat_id: int
    bot: Bot
    downloader: YouTubeDownloader
    settings: Settings
    query: str
    display_name: str
    chat_type: Optional[str] = None
    decade: Optional[str] = None
    
    is_running: bool = field(init=False, default=False)
    playlist: List[TrackInfo] = field(default_factory=list)
    played_ids: Set[str] = field(default_factory=set)
    current_task: Optional[asyncio.Task] = None
    skip_event: asyncio.Event = field(default_factory=asyncio.Event)
    status_message: Optional[Message] = None
    _is_searching: bool = field(init=False, default=False)
    last_wave_change_time: float = field(init=False, default=0.0)
    
    async def start(self):
        if self.is_running: return
        self.is_running = True
        self.last_wave_change_time = time.time()
        self.current_task = asyncio.create_task(self._radio_loop())
        logger.info(f"[{self.chat_id}] 🚀 Эфир: '{self.query}'")

    async def stop(self):
        self.is_running = False
        if self.current_task: self.current_task.cancel()
        await self._delete_status()

    async def skip(self):
        self.skip_event.set()

    async def _handle_forbidden(self):
        self.is_running = False
        self.skip_event.set()

    async def _update_status(self, text: str):
        if not self.is_running: return
        try:
            if self.status_message:
                try: await self.status_message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
                except BadRequest: self.status_message = None
            if not self.status_message:
                self.status_message = await self.bot.send_message(self.chat_id, text, parse_mode=ParseMode.MARKDOWN)
        except Exception: pass

    async def _delete_status(self):
        if self.status_message:
            try: await self.status_message.delete()
            except: pass
            self.status_message = None

    async def _fill_playlist(self):
        if self._is_searching or not self.is_running: return
        self._is_searching = True
        
        variations = [self.query, f"{self.query} mix", f"{self.query} best songs"]
        random.shuffle(variations)
        
        for q in variations:
            if not self.is_running: break
            try:
                tracks = await self.downloader.search(q, decade=self.decade, limit=20)
                new_tracks = [t for t in tracks if t.identifier not in self.played_ids]
                if new_tracks:
                    random.shuffle(new_tracks)
                    self.playlist.extend(new_tracks)
                    break
            except Exception: pass
        
        if len(self.played_ids) > 100: self.played_ids.clear()
        self._is_searching = False

    async def _radio_loop(self):
        while self.is_running:
            try:
                if len(self.playlist) < 3: await self._fill_playlist()
                
                if not self.playlist:
                    await self._update_status("📡 Поиск частоты...")
                    await asyncio.sleep(5)
                    await self._fill_playlist()
                    if not self.playlist:
                        await asyncio.sleep(10)
                        continue

                track = self.playlist.pop(0)
                self.played_ids.add(track.identifier)
                
                # --- ПОПЫТКА ВОСПРОИЗВЕДЕНИЯ ---
                success = await self._play_track(track)
                
                if success:
                    # Если сыграло - ждем конца трека или пропуска
                    wait_time = min(track.duration, 300) if track.duration > 0 else 180
                    try: await asyncio.wait_for(self.skip_event.wait(), timeout=wait_time)
                    except asyncio.TimeoutError: pass 
                else:
                    # !!! ВАЖНОЕ ИЗМЕНЕНИЕ !!!
                    # Если не сыграло (нет на SC) - НЕ ЖДЕМ, СРАЗУ NEXT
                    logger.info(f"[{self.chat_id}] Skip failed track: {track.title}")
                    await asyncio.sleep(0.5) 
                
                self.skip_event.clear()
            except asyncio.CancelledError: break
            except Exception as e: logger.error(f"Loop: {e}"); await asyncio.sleep(5)
        self.is_running = False

    async def _play_track(self, track: TrackInfo) -> bool:
        if not self.is_running: return False
        try:
            await self._update_status(f"⬇️ Ищем на SoundCloud: *{track.title}*...")
            
            result = await self.downloader.download(track.identifier, track_info=track)
            
            if not result or not result.success: 
                # Не нашли на SC
                return False
            
            caption = get_now_playing_message(track, self.display_name)
            
            # Логика отправки файла
            sent = False
            try:
                if result.file_path:
                    with open(result.file_path, 'rb') as f:
                        await self.bot.send_audio(self.chat_id, audio=f, caption=caption, parse_mode=ParseMode.MARKDOWN)
                        sent = True
            except Forbidden: await self._handle_forbidden(); return False
            except Exception: return False
            
            await self._delete_status()
            
            # Удаляем файл
            if result.file_path and result.file_path.exists():
                try: os.unlink(result.file_path)
                except: pass
                
            return sent
        except Exception: return False

class RadioManager:
    def __init__(self, bot: Bot, settings: Settings, downloader: YouTubeDownloader):
        self._bot, self._settings, self._downloader = bot, settings, downloader
        self._sessions: Dict[int, RadioSession] = {}

    async def start(self, chat_id: int, query: str, chat_type: Optional[str] = None, display_name: Optional[str] = None, decade: Optional[str] = None):
        if chat_id in self._sessions: await self._sessions[chat_id].stop()
        
        session = RadioSession(
            chat_id=chat_id, bot=self._bot, downloader=self._downloader, 
            settings=self._settings, query=query, display_name=(display_name or query), 
            decade=decade, chat_type=chat_type
        )
        self._sessions[chat_id] = session
        await session.start()

    async def stop(self, chat_id: int):
        if session := self._sessions.pop(chat_id, None): await session.stop()

    async def skip(self, chat_id: int):
        if session := self._sessions.get(chat_id): await session.skip()
