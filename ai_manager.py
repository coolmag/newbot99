import logging
import json
import asyncio
import re
from google import genai
from config import get_settings

logger = logging.getLogger("ai_manager")
settings = get_settings()

class AIManager:
    def __init__(self):
        self.client = None
        self.is_active = False
        if settings.GOOGLE_API_KEY:
            try:
                self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
                self.is_active = True
                logger.info("✅ AI Ready.")
            except: pass

    async def analyze_message(self, text: str) -> dict:
        if not self.is_active: return self._regex_fallback(text)
        
        # Список моделей "на удачу" - пробуем всё подряд
        # gemini-1.5-flash - самая надежная в 2025
        # gemini-2.0-flash-exp - если доступна
        models = ["gemini-1.5-flash", "gemini-2.0-flash-exp", "gemini-1.5-pro", "gemma-2-9b-it"]
        
        prompt = f"""
        Classify input. Output JSON only: {{"intent": "radio"|"search"|"chat", "query": "string"}}
        Input: {text}
        """
        
        for m in models:
            try:
                res = await self._call_model(m, prompt)
                if res: return self._parse_json(res)
            except: continue
            
        return self._regex_fallback(text)

    async def get_chat_response(self, text: str, user: str, system_prompt: str = "") -> str:
        if not self.is_active: return "..."
        models = ["gemini-1.5-flash", "gemini-2.0-flash-exp"]
        context = f"{system_prompt}\nUser: {text}"
        
        for m in models:
            try:
                res = await self._call_model(m, context)
                if res: return res.strip('"')
            except: continue
            
        return "Связь с космосом потеряна..."

    async def _call_model(self, model, text):
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=model,
            contents=text
        )
        return response.text

    def _regex_fallback(self, text: str) -> dict:
        keywords = ['play', 'радио', 'mix', 'погнали', 'врубай']
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
