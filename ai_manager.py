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
    🧠 AI Manager (2026 Standard).
    Primary: Gemma 3 (12B/4B).
    Fallback: Gemini 2.0 Flash (LTS).
    """
    
    def __init__(self):
        self.client = None
        self.is_active = False
        
        api_key = settings.GOOGLE_API_KEY
        if api_key:
            try:
                self.client = genai.Client(api_key=api_key)
                self.is_active = True
                logger.info("✅ Google AI Connected (2026 Stack).")
            except Exception as e:
                logger.error(f"❌ Failed to init AI: {e}")

    async def analyze_message(self, text: str) -> dict:
        if not self.is_active: return self._regex_fallback(text)

        prompt = f"""
        Classify user message.
        Input: "{text}"
        Output JSON ONLY: {{"intent": "radio"|"search"|"chat", "query": "string or null"}}
        """

        # Актуальный стек моделей 2026
        models = ["gemma-3-12b-it", "gemma-3-4b-it", "gemini-2.0-flash"]

        for model in models:
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model,
                    contents=prompt
                )
                if response.text:
                    res = self._parse_json(response.text)
                    if res: return res
            except Exception as e:
                # Если 503 (перегрузка) или 404 (нет доступа) - идем к следующей
                logger.warning(f"⚠️ Model {model} error: {e}")
                continue

        return self._regex_fallback(text)

    async def get_chat_response(self, text: str, user_name: str, system_prompt: str = "") -> str:
        if not self.is_active: return "Мозг оффлайн 🔌"

        context = f"System: {system_prompt}\nUser ({user_name}): {text}"
        
        # Для чата 12B идеальна, 4B быстрая
        models = ["gemma-3-12b-it", "gemma-3-4b-it", "gemini-2.0-flash"]

        for model in models:
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model,
                    contents=context
                )
                
                answer = response.text
                if answer and len(answer) > 1:
                    return answer.strip('"')
            except Exception as e:
                logger.warning(f"⚠️ Chat {model} failed: {e}")
                continue

        return "Связь с космосом прервалась... 🛸"

    def _regex_fallback(self, text: str) -> dict:
        text_lower = text.lower()
        if any(k in text_lower for k in ['играй', 'play', 'включи', 'радио', 'mix']):
            clean = text_lower.replace('играй','').replace('включи','').replace('радио','').strip()
            return {"intent": "radio", "query": clean or "top hits"}
        return {"intent": "chat", "query": text}

    def _parse_json(self, text: str) -> Optional[dict]:
        try:
            text = text.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{.*\}", text.replace("\n", " "), re.DOTALL)
            if match: return json.loads(match.group(0))
            return json.loads(text)
        except: return None
