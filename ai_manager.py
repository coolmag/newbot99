import logging
import json
import asyncio
import re
from typing import Optional
from google import genai
from config import get_settings

logger = logging.getLogger("ai_manager")
settings = get_settings()

class AIManager:
    """
    🧠 AI Manager (Gemma 3 Edition - 2026).
    Target: Gemma 3 (12B/4B) via Google AI Studio.
    Why: Best free tier limits (no strict RPD).
    """
    
    def __init__(self):
        self.client = None
        self.is_active = False
        
        api_key = settings.GOOGLE_API_KEY
        
        if api_key:
            try:
                # Инициализация клиента v1beta (для новых моделей)
                self.client = genai.Client(api_key=api_key)
                self.is_active = True
                logger.info("✅ Google Client connected (Targeting Gemma 3).")
            except Exception as e:
                logger.error(f"❌ Failed to init Google Client: {e}")
        else:
            logger.warning("⚠️ GOOGLE_API_KEY is missing!")

    async def analyze_message(self, text: str) -> dict:
        if not self.is_active: return self._regex_fallback(text)

        # Промпт адаптирован для open-weights моделей типа Gemma
        prompt = f"""
        Act as a JSON API. 
        Task: Analyze user request for a music bot.
        Input: "{text}"
        
        Output Schema:
        {{
            "intent": "radio" | "search" | "chat",
            "query": "string or null"
        }}
        
        Rules:
        - "radio": if user asks to play a genre, mood, mix, or flow.
        - "search": if user asks for a specific song/artist.
        - "chat": if user says hello, asks how are you, or talks off-topic.
        
        Response (JSON only):
        """

        # Пробуем модели по убыванию "ума"
        # gemma-3-12b-it - золотая середина
        # gemma-3-4b-it - быстрая
        models = ["gemma-3-12b-it", "gemma-3-4b-it", "gemini-1.5-flash"]

        for model in models:
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model,
                    contents=prompt
                )
                
                if response.text:
                    data = self._parse_json(response.text)
                    if data:
                        logger.info(f"🤖 AI ({model}): {data}")
                        return data
            except Exception as e:
                # Логируем ошибку, но пробуем следующую модель
                # 404 означает, что модель недоступна на этом аккаунте/ключе
                if "404" in str(e):
                    logger.warning(f"⚠️ Model {model} not found (404). Trying next...")
                else:
                    logger.warning(f"⚠️ Model {model} error: {e}")
                continue

        return self._regex_fallback(text)

    async def get_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.is_active: return "Мозг отключен 🔌"

        full_prompt = f"{system_prompt}\nUser: {prompt}"
        
        # Для чата можно взять 27B для ума или 12B для скорости
        models = ["gemma-3-12b-it", "gemma-3-27b-it"]

        for model in models:
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model,
                    contents=full_prompt
                )
                if response.text:
                    return response.text
            except Exception as e:
                logger.error(f"Chat error ({model}): {e}")
        
        return "Связь с космосом потеряна... 🛸"

    def _regex_fallback(self, text: str) -> dict:
        text_lower = text.lower()
        radio_keywords = ['радио', 'radio', 'play', 'играй', 'включи', 'mix', 'поток', 'вайб']
        chat_keywords = ['привет', 'как дела', 'кто ты', 'расскажи', 'аврора']

        if any(k in text_lower for k in chat_keywords):
             return {"intent": "chat", "query": text}

        if any(k in text_lower for k in radio_keywords):
            for k in radio_keywords: text_lower = text_lower.replace(k, '')
            return {"intent": "radio", "query": text_lower.strip() or "top hits"}
            
        return {"intent": "search", "query": text}

    def _parse_json(self, text: str) -> Optional[dict]:
        """Умный парсер JSON, так как Gemma любит добавлять лишний текст"""
        try:
            # Gemma может быть многословной, вырезаем JSON
            text = text.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{{.*\}}", text.replace("\n", " "), re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return json.loads(text)
        except: return None