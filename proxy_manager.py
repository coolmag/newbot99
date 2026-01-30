import logging
import random
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

class ProxyManager:
    def __init__(self, project_root: Path):
        self._project_root = project_root
        self._proxy_file = self._project_root / "working_proxies.txt"
        self._proxies: List[str] = []
        self._load_proxies()

    def _load_proxies(self):
        """Загружает рабочие прокси из working_proxies.txt."""
        self._proxies = []
        
        if not self._proxy_file.exists():
            logger.error(f"'{self._proxy_file.name}' not found! No proxies to load.")
            return

        try:
            with open(self._proxy_file, "r") as f:
                for line in f:
                    proxy = line.strip()
                    if proxy:
                        self._proxies.append(proxy)
            
            if not self._proxies:
                logger.warning("working_proxies.txt is empty.")
                return
            
            random.shuffle(self._proxies)
            logger.info(f"Loaded and shuffled {len(self._proxies)} working proxies from {self._proxy_file.name}.")

        except Exception as e:
            logger.error(f"Failed to load proxies from {self._proxy_file.name}: {e}")

    def get_proxy(self) -> Optional[str]:
        """Возвращает следующий прокси из списка, циклически."""
        if not self._proxies:
            return None
        
        # Берем прокси и перекладываем его в конец списка, чтобы обеспечить ротацию
        proxy = self._proxies.pop(0)
        self._proxies.append(proxy)
        
        return proxy

    def report_dead_proxy(self, proxy: str):
        """Удаляет "мертвый" прокси из текущей сессии."""
        if proxy in self._proxies:
            self._proxies.remove(proxy)
            logger.warning(f"Proxy {proxy} reported as dead and removed from the pool. {len(self._proxies)} remaining.")
        
