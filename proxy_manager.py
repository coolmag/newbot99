import logging
import random
from pathlib import Path
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

class ProxyManager:
    def __init__(self, project_root: Path):
        self._project_root = project_root
        self._proxy_file = self._project_root / "working_proxies.txt"
        self._proxies: List[str] = []
        self._load_proxies()

    def _load_proxies(self):
        """Загружает только HTTP/SOCKS прокси. VLESS игнорируем (нужен Xray)."""
        self._proxies = []
        
        if not self._proxy_file.exists():
            logger.warning(f"⚠️ Proxy file not found: {self._proxy_file}")
            return

        try:
            with open(self._proxy_file, "r") as f:
                for line in f:
                    p = line.strip()
                    # Python native lib support only http/socks
                    if p and (p.startswith("http") or p.startswith("socks")):
                        self._proxies.append(p)
            
            if self._proxies:
                random.shuffle(self._proxies)
                logger.info(f"🛡 Loaded {len(self._proxies)} active proxies (HTTP/SOCKS).")
            else:
                logger.warning("⚠️ No compatible (http/socks) proxies found in file.")

        except Exception as e:
            logger.error(f"❌ Proxy load error: {e}")

    def get_proxy(self) -> Optional[str]:
        """Возвращает строку прокси и делает ротацию."""
        if not self._proxies: return None
        
        # Round-robin
        proxy = self._proxies.pop(0)
        self._proxies.append(proxy)
        return proxy

    def get_yt_dlp_proxy_opts(self) -> Dict:
        """Формирует конфиг для yt-dlp"""
        proxy = self.get_proxy()
        if proxy:
            # yt-dlp принимает ключ http_proxy даже для socks5
            return {'http_proxy': proxy}
        return {}

    def report_dead_proxy(self, proxy: str):
        """Удаляет битый прокси из ротации"""
        if proxy in self._proxies:
            self._proxies.remove(proxy)
            logger.warning(f"⚰️ Proxy died: {proxy}. Remaining: {len(self._proxies)}")
