import logging
import json
import asyncio
import re
from google import genai
from google.genai import types
from config import get_settings

logger = logging.getLogger("ai_manager")
settings = get_settings()

class AIManager:
    """
    🧠 AI Manager (2026 Modern).
    Targets: 
    1. gemini-2.0-flash-lite-preview-02-05 (Fastest, Newest)
    2. gemini-2.0-flash (Standard)
    3. gemma-3-12b-it (Open Weights Backup)
    """
    
    def __init__(self):
        self.client = None
        self.is_active = False
        
        if settings.GOOGLE_API_KEY:
            try:
                # Используем v1beta для доступа к preview моделям
                self.client = genai.Client(
                    api_key=settings.GOOGLE_API_KEY,
                    http_options={'api_version': 'v1beta'}
                )
                self.is_active = True
                logger.info("✅ AI Ready (2026 Stack).")
            except: pass

    async def analyze_message(self, text: str) -> dict:
        """Определяем намерение (Музыка или Чат)"""
        if not self.is_active: return self._regex_fallback(text)
        
        # Актуальный список на 2026 год
        models = [
            "gemini-2.0-flash-lite-preview-02-05", # Самая свежая
            "gemini-2.0-flash",                     # Стандарт
            "gemma-3-12b-it"                        # Резерв
        ]
        
        prompt = f"""
        Act as a classifier. 
        Input: "{text}"
        Rules:
        - "radio": genre, mood, 'play music', 'mix', 'погнали', 'врубай'.
        - "search": specific song name.
        - "chat": hello, conversation, questions.
        
        Output JSON ONLY: {{"intent": "radio"|"search"|"chat", "query": "string"}}
        """
        
        for m in models:
            try:
                res = await self._call_model(m, prompt)
                if res: 
                    data = self._parse_json(res)
                    if data: return data
            except: 
                continue # Если модель 404/503 - пробуем следующую молча
            
        # Если все ИИ умерли - фоллбэк на алгоритмы
        return self._regex_fallback(text)

    async def get_chat_response(self, text: str, user: str, system_prompt: str = "") -> str:
        """Генерация ответа в чате"""
        if not self.is_active: return "..."
        
        models = [
            "gemini-2.0-flash-lite-preview-02-05", 
            "gemini-2.0-flash"
        ]
        
        context = f"System: {system_prompt}\nUser ({user}): {text}"
        
        for m in models:
            try:
                res = await self._call_model(m, context)
                if res: return res.strip('"')
            except: continue
            
        return "Связь с космосом прервалась... 🛸"

    async def _call_model(self, model, text):
        # Отключаем лишние повторы для скорости
        config = types.GenerateContentConfig(
            candidate_count=1,
            temperature=0.7
        )
        
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=model,
            contents=text,
            config=config
        )
        return response.text

    def _regex_fallback(self, text: str) -> dict:
        """Надежный запасной вариант (Regex)"""
        text_lower = text.lower()
        # Расширенный список слов-триггеров
        radio_keywords = [
            'играй', 'play', 'включи', 'радио', 'mix', 
            'погнали', 'врубай', 'давай', 'запускай', 'хочу'
        ]
        
        if any(k in text_lower for k in radio_keywords):
            clean = text_lower
            for k in radio_keywords: clean = clean.replace(k, '')
            query = clean.strip()
            return {"intent": "radio", "query": query if len(query) > 2 else "top hits"}
        
        return {"intent": "chat", "query": text}

    def _parse_json(self, text: str):
        try:
            match = re.search(r"\{.*\}", text.replace("\n", " "), re.DOTALL)
            return json.loads(match.group(0)) if match else json.loads(text)
        except: return None
