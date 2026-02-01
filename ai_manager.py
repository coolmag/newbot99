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
    🧠 AI Manager (Gemma 3 Edition).
    Strictly uses user-provided model list:
    - gemma-3-12b (Primary)
    - gemma-3-4b (Fast Fallback)
    - gemma-3-27b (Smart Fallback)
    """
    
    def __init__(self):
        self.client = None
        self.is_active = False
        
        if settings.GOOGLE_API_KEY:
            try:
                # Инициализация клиента
                self.client = genai.Client(
                    api_key=settings.GOOGLE_API_KEY,
                    http_options={'api_version': 'v1beta'}
                )
                self.is_active = True
                logger.info("✅ AI Ready (Gemma 3 Family).")
            except Exception as e:
                logger.error(f"❌ Init Error: {e}")

    async def analyze_message(self, text: str) -> dict:
        """Классификация намерения"""
        if not self.is_active: return self._regex_fallback(text)
        
        # Строгий список из вашего промпта
        models = ["gemma-3-12b", "gemma-3-4b", "gemma-3-27b"]
        
        prompt = f"""
        Act as a music bot classifier.
        User Input: "{text}"
        
        Rules:
        1. "radio": play music, genre, mood, mix, 'погнали', 'врубай'.
        2. "search": specific song name.
        3. "chat": conversation, hello, questions.
        
        Return JSON ONLY: {{"intent": "radio"|"search"|"chat", "query": "string"}}
        """
        
        for m in models:
            try:
                # Gemma любит инструкции в prompt, а не system_instruction
                res = await self._call_model(m, prompt)
                if res: 
                    data = self._parse_json(res)
                    if data: return data
            except Exception as e:
                logger.warning(f"⚠️ {m} error: {e}")
                continue
            
        return self._regex_fallback(text)

    async def get_chat_response(self, text: str, user: str, system_prompt: str = "") -> str:
        """Болталка"""
        if not self.is_active: return "..."
        
        # Для чата 12b оптимальна, 27b умнее
        models = ["gemma-3-12b", "gemma-3-27b", "gemma-3-4b"]
        
        full_prompt = f"{system_prompt}\nUser ({user}): {text}\nResponse:"
        
        for m in models:
            try:
                res = await self._call_model(m, full_prompt)
                if res: return res.strip('" ')
            except: continue
            
        return "Связь с космосом прервалась... 🛸"

    async def _call_model(self, model, text):
        # Конфиг для Gemma 3
        config = types.GenerateContentConfig(
            candidate_count=1,
            temperature=0.7,
            top_p=0.95
        )
        
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=model,
            contents=text,
            config=config
        )
        return response.text

    def _regex_fallback(self, text: str) -> dict:
        text_lower = text.lower()
        radio_keywords = [
            'играй', 'play', 'включи', 'радио', 'mix', 
            'погнали', 'врубай', 'давай', 'хочу', 'заводи'
        ]
        
        if any(k in text_lower for k in radio_keywords):
            clean = text_lower
            for k in radio_keywords: clean = clean.replace(k, '')
            return {"intent": "radio", "query": clean.strip() or "top hits"}
        
        return {"intent": "chat", "query": text}

    def _parse_json(self, text: str):
        try:
            # Gemma может добавить markdown
            text = text.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{.*\}", text.replace("\n", " "), re.DOTALL)
            return json.loads(match.group(0)) if match else json.loads(text)
        except: return None
