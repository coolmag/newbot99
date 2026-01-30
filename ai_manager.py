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
    🧠 AI Manager (Google Gemma Edition).
    Primary: Gemma 2 (9b-it) via Google GenAI.
    Backup: Gemini 1.5 Flash.
    """
    
    def __init__(self):
        self.client = None
        self.is_active = False
        
        if settings.GOOGLE_API_KEY:
            try:
                self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
                self.is_active = True
                logger.info("✅ Google Client connected. Target: Gemma 2.")
            except Exception as e:
                logger.error(f"❌ Failed to init Google Client: {e}")
        else:
            logger.warning("⚠️ GOOGLE_API_KEY not found!")

    async def analyze_message(self, text: str) -> dict:
        """Анализ намерения: Gemma 2"""
        if not self.is_active: return self._regex_fallback(text)

        # Gemma лучше понимает простой промпт без спец. флагов JSON
        prompt = f"""
        Task: Analyze user message for a music bot.
        Message: "{text}"
        
        Output ONLY valid JSON:
        {{
            "intent": "radio" (play music/mix), "search" (specific song), or "chat" (talk),
            "query": "search term or null"
        }}
        Do not write markdown or explanations. Just JSON.
        """

        # Пробуем Gemma 2 (9B - оптимальная)
        # Если не выйдет - откатимся на Gemini
        models = ["gemma-2-9b-it", "gemma-2-27b-it", "gemini-1.5-flash"]

        for model in models:
            try:
                # Gemma не поддерживает config={'response_mime_type': 'application/json'} так хорошо,
                # как Gemini, поэтому убираем конфиг и парсим текст вручную.
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
                logger.warning(f"⚠️ Model {model} failed: {e}")
                continue

        return self._regex_fallback(text)

    async def get_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        """Болталка: Gemma 2"""
        if not self.is_active: return "AI не активен 🔌"

        full_prompt = f"{system_prompt}\nUser: {prompt}"
        
        # Для чата Gemma 2 9b отличный выбор
        models = ["gemma-2-9b-it", "gemini-1.5-flash"]

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
        """Запасной вариант без AI"""
        text_lower = text.lower()
        radio_keywords = ['радио', 'radio', 'play', 'играй', 'включи', 'mix', 'поток']
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
            # Находим первую { и последнюю }
            match = re.search(r"\{.*\}", text.replace("\n", " "), re.DOTALL)
            if match:
                clean_json = match.group(0)
                return json.loads(clean_json)
        except: pass
        return None
