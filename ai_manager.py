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
    🧠 AI Manager (Experimental 2026).
    Target: gemini-2.0-flash-lite-preview-02-05 (New Lite model).
    """
    
    def __init__(self):
        self.client = None
        self.is_active = False
        
        if settings.GOOGLE_API_KEY:
            try:
                # Инициализация с отключенным AFC (чтобы не спамил)
                self.client = genai.Client(
                    api_key=settings.GOOGLE_API_KEY,
                    http_options={'api_version': 'v1beta'}
                )
                self.is_active = True
                logger.info("✅ AI Ready (Gemini 2.5 Lite).")
            except: pass

    async def analyze_message(self, text: str) -> dict:
        if not self.is_active: return self._regex_fallback(text)
        
        # Актуальные модели на начало 2026
        models = [
            "gemini-2.0-flash-lite-preview-02-05", 
            "gemini-2.0-flash", 
            "gemini-1.5-flash"
        ]
        
        prompt = f"""
        Classify input. Output JSON only: {{"intent": "radio"|"search"|"chat", "query": "string"}}
        Input: {text}
        """
        
        for m in models:
            try:
                res = await self._call_model(m, prompt)
                if res: return self._parse_json(res)
            except Exception as e:
                logger.warning(f"⚠️ Model {m} error: {e}")
                continue
            
        return self._regex_fallback(text)

    async def get_chat_response(self, text: str, user: str, system_prompt: str = "") -> str:
        if not self.is_active: return "..."
        
        models = [
            "gemini-2.0-flash-lite-preview-02-05", 
            "gemini-2.0-flash"
        ]
        
        context = f"{system_prompt}\nUser: {text}"
        
        for m in models:
            try:
                res = await self._call_model(m, context)
                if res: return res.strip('"')
            except: continue
            
        return "Связь с космосом потеряна..."

    async def _call_model(self, model, text):
        # Отключаем встроенный ретрай, чтобы быстрее перебирать модели
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
        keywords = ['play', 'радио', 'mix', 'погнали', 'врубай', 'давай']
        if any(k in text.lower() for k in keywords):
            clean = text.lower()
            for k in keywords: clean = clean.replace(k, '')
            return {"intent": "radio", "query": clean.strip() or "top hits"}
        return {"intent": "chat", "query": text}

    def _parse_json(self, text: str):
        try:
            match = re.search(r"\{.*\}", text.replace("\n", " "), re.DOTALL)
            return json.loads(match.group(0)) if match else json.loads(text)
        except: return None
