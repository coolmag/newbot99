import asyncio
import logging
import random
import os
import time
import json
from pathlib import Path
from typing import List, Optional, Dict, Set
from dataclasses import dataclass, field
from telegram import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import BadRequest

from config import Settings
from models import TrackInfo, DownloadResult
from youtube import YouTubeDownloader

# Загружаем каталог
try:
    with open(Path(__file__).parent / "genres.json", "r", encoding="utf-8") as f:
        MUSIC_CATALOG = json.load(f)
except Exception as e:
    logging.error(f"FATAL: Could not load genres.json: {e}")
    MUSIC_CATALOG = {}

logger = logging.getLogger("radio")

def format_duration(seconds: int) -> str:
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d}"

def get_now_playing_message(track: TrackInfo, genre_name: str) -> str:
    # Очистка от markdown символов
    title = track.title.replace('*', '').replace('_', '').strip()
    artist = track.uploader.replace('*', '').replace('_', '').strip()
    return f"💿 *{title}*\n👤 {artist}\n⏱ {format_duration(track.duration)} | 📻 _{genre_name}_"

@dataclass
class RadioSession:
    chat_id: int
    bot: Bot
    downloader: YouTubeDownloader
    settings: Settings
    query: str
    display_name: str
    chat_type: Optional[str] = None
    
    is_running: bool = field(init=False, default=False)
    playlist: List[TrackInfo] = field(default_factory=list)
    played_ids: Set[str] = field(default_factory=set)
    current_task: Optional[asyncio.Task] = None
    skip_event: asyncio.Event = field(default_factory=asyncio.Event)
    status_message: Optional[Message] = None
    _is_searching: bool = field(init=False, default=False)
    last_wave_change_time: float = field(init=False, default=0.0)
    consecutive_errors: int = field(init=False, default=0)

    async def start(self):
        if self.is_running: return
        self.is_running = True
        self.last_wave_change_time = time.time()
        self.consecutive_errors = 0
        self.current_task = asyncio.create_task(self._radio_loop())
        logger.info(f"[{self.chat_id}] 🚀 Эфир запущен: '{self.query}'")

    async def stop(self):
        self.is_running = False
        if self.current_task: self.current_task.cancel()
        await self._delete_status()

    async def skip(self):
        self.skip_event.set()

    async def change_wave_random(self):
        """Меняет волну на случайную."""
        try:
            # Собираем все варианты
            all_queries = []
            def collect(node):
                if isinstance(node, dict):
                    if "query" in node: all_queries.append(node)
                    if "children" in node:
                        for k, v in node["children"].items(): collect(v)
            
            for k, v in MUSIC_CATALOG.items(): collect(v)

            if not all_queries: return

            # Выбираем новую, отличную от текущей
            opts = [x for x in all_queries if x.get("query") != self.query] or all_queries
            new_wave = random.choice(opts)
            
            self.query = new_wave["query"]
            self.display_name = new_wave.get("name", "Random Mix")
            
            # Сброс
            self.playlist.clear()
            self.played_ids.clear()
            self.consecutive_errors = 0
            self.last_wave_change_time = time.time()
            
            await self.bot.send_message(
                self.chat_id, 
                f"🔄 *Авто-смена пластинки!*\n📡 Волнa: *{self.display_name}*", 
                parse_mode=ParseMode.MARKDOWN
            )
            # Сразу ищем треки
            await self._fill_playlist()

        except Exception as e:
            logger.error(f"Change wave error: {e}")

    async def _fill_playlist(self):
        if self._is_searching or not self.is_running: return
        self._is_searching = True
        
        try:
            # Пробуем разные вариации запроса, чтобы найти хоть что-то
            variations = [self.query, f"{self.query} best", f"{self.query} hits"]
            random.shuffle(variations)
            
            found = False
            for q in variations:
                if not self.is_running: break
                try:
                    tracks = await self.downloader.search(q, limit=20)
                    new_tracks = [t for t in tracks if t.identifier not in self.played_ids]
                    
                    if new_tracks:
                        random.shuffle(new_tracks)
                        self.playlist.extend(new_tracks)
                        found = True
                        break
                except Exception: continue
            
            # ЕСЛИ ПУСТО -> МЕНЯЕМ ВОЛНУ
            if not found and not self.playlist:
                logger.warning(f"[{self.chat_id}] Жанр пуст. Ротация.")
                self._is_searching = False
                await self.change_wave_random()
                return

        finally:
            self._is_searching = False

    async def _radio_loop(self):
        while self.is_running:
            try:
                # 1. ТАЙМЕР (1 час)
                if time.time() - self.last_wave_change_time > 3600:
                    await self.change_wave_random()

                # 2. ПОПОЛНЕНИЕ
                if len(self.playlist) < 3: 
                    await self._fill_playlist()
                
                # Если все равно пусто
                if not self.playlist:
                    await self._update_status("📡 Поиск сигнала...")
                    await asyncio.sleep(5)
                    if not self.playlist:
                        await self.change_wave_random()
                        continue

                # 3. ТРЕК
                track = self.playlist.pop(0)
                self.played_ids.add(track.identifier)
                if len(self.played_ids) > 200: self.played_ids = set(list(self.played_ids)[100:])

                # 4. ВОСПРОИЗВЕДЕНИЕ
                success = await self._play_track(track)
                
                if success:
                    self.consecutive_errors = 0
                    # Ждем конца трека или пропуска
                    wait = min(track.duration, 300) if track.duration > 0 else 180
                    try: await asyncio.wait_for(self.skip_event.wait(), timeout=wait)
                    except asyncio.TimeoutError: pass 
                else:
                    self.consecutive_errors += 1
                    logger.warning(f"[{self.chat_id}] Ошибка воспроизведения ({self.consecutive_errors} подряд)")
                    
                    # Если 5 ошибок подряд — жанр "сломан" (на SC нет треков), меняем
                    if self.consecutive_errors >= 5:
                        logger.warning("Too many errors. Rotating.")
                        await self.change_wave_random()
                    else:
                        await asyncio.sleep(1) # Быстрый скип
                
                self.skip_event.clear()

            except asyncio.CancelledError: break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(5)
        
        self.is_running = False

    async def _play_track(self, track: TrackInfo) -> bool:
        if not self.is_running: return False
        try:
            await self._update_status(f"⬇️ Загрузка: *{track.title}*...")
            
            result = await self.downloader.download(track.identifier, track_info=track)
            
            if not result or not result.success: return False
            
            caption = get_now_playing_message(track, self.display_name)
            
            # Создаем клавиатуру
            keyboard = None
            if self.settings.BASE_URL:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎧 Веб-плеер", url=self.settings.BASE_URL)
                ]])

            if result.file_path:
                try:
                    with open(result.file_path, 'rb') as f:
                        await self.bot.send_audio(
                            self.chat_id, 
                            audio=f, 
                            caption=caption, 
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=keyboard,
                            read_timeout=60,
                            write_timeout=60
                        )
                    await self._delete_status()
                    try: os.unlink(result.file_path)
                    except: pass
                    return True
                except Exception: return False
            return False
        except Exception: return False

    async def _update_status(self, text: str):
        if not self.is_running: return
        try:
            if not self.status_message:
                self.status_message = await self.bot.send_message(self.chat_id, text, parse_mode=ParseMode.MARKDOWN)
            else:
                try: await self.status_message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
                except BadRequest: self.status_message = None
        except Exception: pass

    async def _delete_status(self):
        if self.status_message:
            try: await self.status_message.delete()
            except: pass
            self.status_message = None

class RadioManager:
    def __init__(self, bot: Bot, settings: Settings, downloader: YouTubeDownloader):
        self._bot = bot
        self._settings = settings
        self._downloader = downloader
        self._sessions: Dict[int, RadioSession] = {}

    async def start(self, chat_id: int, query: str, chat_type: Optional[str] = None, display_name: Optional[str] = None):
        if chat_id in self._sessions: 
            await self._sessions[chat_id].stop()
        
        session = RadioSession(
            chat_id=chat_id, bot=self._bot, downloader=self._downloader, 
            settings=self._settings, query=query, display_name=(display_name or query), 
            chat_type=chat_type
        )
        self._sessions[chat_id] = session
        await session.start()

    async def stop(self, chat_id: int):
        if session := self._sessions.pop(chat_id, None): 
            await session.stop()

    async def skip(self, chat_id: int):
        if session := self._sessions.get(chat_id): 
            await session.skip()
