import logging
import json
import re
import asyncio
from typing import Optional, List
from google import genai
from google.genai import types
from config import get_settings

logger = logging.getLogger("ai_manager")
settings = get_settings()

class AIManager:
    """
    🧠 AI Manager (Auto-Discovery 2026).
    Автоматически находит рабочую модель в аккаунте Google.
    """
    
    def __init__(self):
        self.client = None
        self.active_model = None
        self.is_active = False
        
        # Приоритет: Сначала Instruct (it) версии Gemma 3, потом Flash
        self.PRIORITY_PATTERNS = [
            r"gemma-3-.*-it",    # Gemma 3 Instruct
            r"gemma-2-.*-it",    # Gemma 2 Instruct
            r"gemini-2.0-flash", # New Flash
            r"gemini-1.5-flash", # Old Faithful
            r"gemini-.*-flash"    # Any Flash
        ]
        
        self._init_client()

    def _init_client(self):
        if not settings.GOOGLE_API_KEY:
            logger.warning("⚠️ GOOGLE_API_KEY missing. AI Disabled.")
            return

        try:
            self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            
            # 🔍 AUTO-DISCOVERY
            all_models = self._list_available_models()
            self.active_model = self._pick_best_model(all_models)
            
            if self.active_model:
                self.is_active = True
                logger.info(f"✅ AI Online. Using Model: {self.active_model}")
            else:
                logger.warning("⚠️ AI Connected, but no suitable generation models found.")
                
        except Exception as e:
            logger.error(f"❌ AI Init Critical Error: {e}")

    def _list_available_models(self) -> List[str]:
        try:
            # Получаем список всех моделей
            models = list(self.client.models.list_models())
            names = [m.name for m in models]
            return names
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return ["gemini-1.5-flash"] # Fallback

    def _pick_best_model(self, available: List[str]) -> Optional[str]:
        # Убираем префикс 'models/' для матчинга
        clean_map = {name.replace("models/", ""): name for name in available}
        clean_names = list(clean_map.keys())
        
        for pattern in self.PRIORITY_PATTERNS:
            for name in clean_names:
                if re.search(pattern, name, re.IGNORECASE):
                    return clean_map[name]
        
        # Если ничего не совпало, ищем хоть что-то с 'generateContent' (обычно это flash или pro)
        for name in clean_names:
            if "flash" in name or "pro" in name:
                return clean_map[name]
                
        return clean_map[clean_names[0]] if clean_names else None

    async def analyze_message(self, text: str) -> dict:
        """Классификация намерения"""
        if not self.is_active: return self._regex_fallback(text)
        
        prompt = f"""
        Classify user intent.
        Input: "{text}"
        Possible intents:
        1. "radio": play music, 'play', 'mix', genre names.
        2. "search": specific song name.
        3. "chat": conversation, questions.
        
        Return JSON: {{"intent": "radio"|"search"|"chat", "query": "cleaned search term"}}
        """
        
        try:
            res = await self._call_model(prompt)
            if res:
                data = self._parse_json(res)
                if data: return data
        except Exception:
            pass # Silent fail to fallback
            
        return self._regex_fallback(text)

    async def get_chat_response(self, text: str, user: str, system_prompt: str = "") -> str:
        """Чат"""
        if not self.is_active: return "System offline."
        
        prompt = f"{system_prompt}\nUser: {text}\n(Keep it short, max 2 sentences)"
        try:
            return await self._call_model(prompt) or "..."
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return "Error."

    async def _call_model(self, text: str) -> str:
        if not self.active_model: return ""
        try:
            config = types.GenerateContentConfig(
                candidate_count=1,
                temperature=0.7,
                max_output_tokens=200
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.active_model,
                contents=text,
                config=config
            )
            return response.text.strip() if response.text else ""
        except Exception as e:
            logger.warning(f"AI Call failed ({self.active_model}): {e}")
            return ""

    def _regex_fallback(self, text: str) -> dict:
        text_lower = text.lower()
        radio_keywords = ['играй', 'play', 'включи', 'радио', 'mix', 'погнали', 'врубай']
        
        if any(k in text_lower for k in radio_keywords):
            clean = text_lower
            for k in radio_keywords: clean = clean.replace(k, '')
            return {"intent": "radio", "query": clean.strip() or "top hits"}
        return {"intent": "chat", "query": text}

    def _parse_json(self, text: str):
        try:
            text = re.sub(r"```json|```", "", text).strip()
            match = re.search(r"\{.*\}", text.replace("\n", " "), re.DOTALL)
            return json.loads(match.group(0)) if match else json.loads(text)
        except: return None
