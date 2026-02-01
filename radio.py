import asyncio
import logging
import random
import os
from typing import List, Optional, Dict, Set
from dataclasses import dataclass, field
from telegram import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.error import BadRequest, RetryAfter, Forbidden
from config import Settings
from models import TrackInfo, DownloadResult
from youtube import YouTubeDownloader
from catalog import FULL_CATALOG 

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
    
    async def start(self):
        if self.is_running: return
        self.is_running = True
        self.current_task = asyncio.create_task(self._radio_loop())
        logger.info(f"[{self.chat_id}] 🚀 Эфир запущен: '{self.query}'")

    async def stop(self):
        self.is_running = False
        if self.current_task: self.current_task.cancel()
        await self._delete_status()
        logger.info(f"[{self.chat_id}] 🛑 Эфир остановлен.")

    async def skip(self):
        self.skip_event.set()

    async def _handle_forbidden(self):
        logger.error(f"[{self.chat_id}] ⛔️ Бот заблокирован. Стоп.")
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
        except Forbidden: await self._handle_forbidden()
        except Exception: self.status_message = None

    async def _delete_status(self):
        if self.status_message:
            try: await self.status_message.delete()
            except: pass
            self.status_message = None

    async def _fill_playlist(self):
        if self._is_searching or not self.is_running: return
        self._is_searching = True
        
        # Вариации запросов
        variations = [self.query, f"{self.query} best", f"{self.query} mix"]
        if self.decade: variations.append(f"{self.query} {self.decade}")
        random.shuffle(variations)
        
        for q in variations:
            if not self.is_running: break
            try:
                tracks = await self.downloader.search(q, decade=self.decade, limit=20)
                new_tracks = [t for t in tracks if t.identifier not in self.played_ids]
                
                if new_tracks:
                    random.shuffle(new_tracks)
                    self.playlist.extend(new_tracks)
                    logger.info(f"[{self.chat_id}] +{len(new_tracks)} треков.")
                    break
            except Exception: continue
        
        if not self.playlist and len(self.played_ids) > 5:
             self.played_ids.clear() # Сброс истории, если тупик

        self._is_searching = False

    async def _radio_loop(self):
        while self.is_running:
            try:
                if len(self.playlist) < 3: await self._fill_playlist()
                
                if not self.playlist:
                    await self._update_status("📡 Поиск музыки...")
                    await asyncio.sleep(5)
                    continue

                track = self.playlist.pop(0)
                self.played_ids.add(track.identifier)
                if len(self.played_ids) > 200: 
                    self.played_ids = set(list(self.played_ids)[100:])

                success = await self._play_track(track)
                
                if success:
                    wait_time = min(track.duration, 300) if track.duration > 0 else 180
                    try: await asyncio.wait_for(self.skip_event.wait(), timeout=wait_time)
                    except asyncio.TimeoutError: pass 
                else: await asyncio.sleep(2)
                
                self.skip_event.clear()
            except asyncio.CancelledError: break
            except Exception as e: logger.error(f"Loop error: {e}"); await asyncio.sleep(5)
        self.is_running = False

    async def _play_track(self, track: TrackInfo) -> bool:
        result = None 
        if not self.is_running: return False
        try:
            await self._update_status(f"⬇️ Загрузка: *{track.title}*...")
            result = await self.downloader.download(track.identifier, track_info=track)
            
            if not result or not result.success: return False
            
            caption = get_now_playing_message(track, self.display_name)
            
            # Пробуем отправить кэшированный file_id
            cached_id = await self.downloader._cache.get(f"file_id:{track.identifier}")
            if cached_id:
                try:
                    await self.bot.send_audio(self.chat_id, audio=cached_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
                    await self._delete_status()
                    return True
                except: pass

            # Отправляем файл
            if result.file_path:
                with open(result.file_path, 'rb') as f:
                    msg = await self.bot.send_audio(self.chat_id, audio=f, caption=caption, parse_mode=ParseMode.MARKDOWN)
                    if msg.audio:
                        await self.downloader._cache.set(f"file_id:{track.identifier}", msg.audio.file_id)
            
            await self._delete_status()
            return True
        except Forbidden: await self._handle_forbidden(); return False
        except Exception as e:
            logger.error(f"Play error: {e}")
            return False
        finally:
            if result and result.file_path and os.path.exists(result.file_path):
                try: os.unlink(result.file_path)
                except: pass

class RadioManager:
    def __init__(self, bot: Bot, settings: Settings, downloader: YouTubeDownloader):
        self._bot, self._settings, self._downloader = bot, settings, downloader
        self._sessions: Dict[int, RadioSession] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        self._locks.setdefault(chat_id, asyncio.Lock())
        return self._locks[chat_id]

    async def start(self, chat_id: int, query: str, chat_type: str = None):
        async with self._get_lock(chat_id):
            if chat_id in self._sessions: await self._sessions[chat_id].stop()
            
            display_name = query
            decade = None
            
            if query == "random": 
                query, decade, display_name = self._get_random_query()

            session = RadioSession(
                chat_id=chat_id, bot=self._bot, downloader=self._downloader, 
                settings=self._settings, query=query, display_name=display_name, 
                decade=decade, chat_type=chat_type
            )
            self._sessions[chat_id] = session
            await session.start()

    async def stop(self, chat_id: int):
        async with self._get_lock(chat_id):
            if session := self._sessions.pop(chat_id, None): await session.stop()

    def _get_random_query(self) -> tuple[str, Optional[str], str]:
        all_queries = []
        def extract(node):
            if isinstance(node, dict):
                if "query" in node:
                    all_queries.append((node["query"], node.get("decade"), node.get("name", "Unknown")))
                for k, v in node.items(): extract(v)
            elif isinstance(node, list):
                for item in node: extract(item)

        extract(FULL_CATALOG)
        return random.choice(all_queries) if all_queries else ("top hits", None, "Random")