import logging
import json
import asyncio
import re
from typing import Optional, Dict

# ИЗМЕНЕНО: Правильный импорт
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from config import get_settings

logger = logging.getLogger("ai_manager")

class AIManager:
    """
    🧠 AI Manager (Gemma 3 Edition - 2026, v2 - Patched).
    Исправлена критическая ошибка инициализации клиента Google GenAI.
    Код теперь использует правильные методы: genai.configure и genai.GenerativeModel.
    """
    
    def __init__(self):
        self.is_active = False
        settings = get_settings()
        api_key = settings.GOOGLE_API_KEY
        
        if api_key:
            try:
                # ИСПРАВЛЕНО: Используем genai.configure для аутентификации
                genai.configure(api_key=api_key)
                self.is_active = True
                logger.info("✅ Google GenAI configured successfully (Targeting Gemma/Gemini).")
            except Exception as e:
                logger.error(f"❌ Failed to configure Google GenAI: {e}")
        else:
            logger.warning("⚠️ GOOGLE_API_KEY is missing!")

    async def analyze_message(self, text: str) -> Dict:
        if not self.is_active: return self._regex_fallback(text)

        prompt = f"""
        Act as a JSON API. Task: Analyze user request for a music bot. Input: "{text}"
        Output Schema: {{ "intent": "radio" | "search" | "chat", "query": "string or null" }}
        Rules:
        - "radio": if user asks to play a genre, mood, mix, or flow.
        - "search": if user asks for a specific song/artist.
        - "chat": if user says hello, asks how are you, or talks off-topic.
        Response (JSON only):
        """

        # ИСПРАВЛЕНО: Указание формата JSON для лучшего вывода
        generation_config = GenerationConfig(response_mime_type="application/json")
        models = ["gemma-3-12b-it", "gemma-3-4b-it"] # Только Gemma 3

        for model_name in models:
            try:
                # ИСПРАВЛЕНО: Создаем модель и используем async метод
                model = genai.GenerativeModel(model_name)
                response = await model.generate_content_async(
                    contents=prompt,
                    generation_config=generation_config
                )
                
                # Gemini API с application/json сразу возвращает валидный JSON
                data = self._parse_json(response.text)
                if data and data.get("intent"):
                    logger.info(f"🤖 AI ({model_name}): {data}")
                    return data
            except Exception as e:
                logger.warning(f"⚠️ Model {model_name} error: {e}. Trying next...")
                continue

        return self._regex_fallback(text)

    async def get_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.is_active: return "Мозг отключен 🔌"

        # ИСПРАВЛЕНО: Модели для чата
        models = ["gemma-3-12b-it", "gemma-3-27b-it"]
        
        for model_name in models:
            try:
                # ИСПРАВЛЕНО: system_prompt передается напрямую
                model = genai.GenerativeModel(model_name, system_instruction=system_prompt)
                response = await model.generate_content_async(contents=prompt)
                
                if response.text:
                    return response.text
            except Exception as e:
                logger.error(f"Chat error ({model_name}): {e}. Trying next...")
        
        return "Связь с космосом потеряна... 🛸"

    def _regex_fallback(self, text: str) -> Dict:
        text_lower = text.lower()
        radio_keywords = ['радио', 'radio', 'play', 'играй', 'включи', 'mix', 'поток', 'вайб']
        chat_keywords = ['привет', 'как дела', 'кто ты', 'расскажи', 'аврора']

        if any(k in text_lower for k in chat_keywords):
             return {"intent": "chat", "query": text}

        if any(k in text_lower for k in radio_keywords):
            for k in radio_keywords: text_lower = text_lower.replace(k, '')
            return {"intent": "radio", "query": text_lower.strip() or "top hits"}
            
        return {"intent": "search", "query": text}

    def _parse_json(self, text: str) -> Optional[Dict]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Резервный парсер, если модель не вернула чистый JSON
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try: return json.loads(match.group(0))
                except: return None
            return None
