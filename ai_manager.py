import logging
import json
import re
import google.generativeai as genai
from typing import Optional, Dict

from config import get_settings

logger = logging.getLogger("ai_manager")

try:
    from google.generativeai.types import GenerationConfig
except ImportError:
    GenerationConfig = genai.GenerationConfig

AURORA_SYSTEM_PROMPT = """
Ты — Аврора, ИИ-диджей в Телеграм-боте.
Твой стиль: дерзкая, веселая, используешь эмодзи (🎧, 🛸, 🎸).
Ты не ассистент, ты — фанатка музыки.
Отвечай кратко (до 2 предложений).
"""

class AIManager:
    def __init__(self):
        self.is_active = False
        settings = get_settings()
        api_key = settings.GOOGLE_API_KEY
        
        if api_key:
            try:
                genai.configure(api_key=api_key)
                # Используем стандартную модель, без изысков
                self.model = genai.GenerativeModel('gemini-2.0-flash') 
                self.is_active = True
                logger.info("✅ Gemini AI activated.")
            except Exception as e:
                logger.error(f"❌ Gemini config failed: {e}")
        else:
            logger.warning("⚠️ GOOGLE_API_KEY missing.")

    async def analyze_message(self, text: str) -> Dict:
        if not self.is_active: return self._regex_fallback(text)
            
        try:
            prompt = f"""
            Classify intent:
            1. 'search' (specific song/artist)
            2. 'radio' (genre/mood/vibe/mix/hits)
            3. 'chat' (general conversation)
            
            Format: INTENT: <intent> | QUERY: <query>
            
            Input: "{text}"
            """
            
            response = await self.model.generate_content_async(
                prompt,
                generation_config=GenerationConfig(temperature=0.1)
            )
            raw = response.text.strip()
            
            intent = "chat"
            query = text
            if "INTENT:" in raw:
                if "search" in raw: intent = "search"
                elif "radio" in raw: intent = "radio"
                
                if "| QUERY:" in raw:
                    query = raw.split("| QUERY:")[1].strip()
            
            return {"intent": intent, "query": query}

        except Exception as e:
            logger.warning(f"[AI] Error: {e}")
            return self._regex_fallback(text)

    async def get_chat_response(self, user_text: str, system_prompt: str = "") -> str:
        if not self.is_active: return "Мозг оффлайн 🔌"
        
        sp = system_prompt or AURORA_SYSTEM_PROMPT
        try:
            chat = self.model.start_chat(history=[
                {"role": "user", "parts": [sp + "\nHi!"]},
                {"role": "model", "parts": ["Привет! Я готова! 🎧"]}
            ])
            response = await chat.send_message_async(user_text)
            return response.text
        except Exception:
            return "Помехи в эфире... 🛸"

    def _regex_fallback(self, text: str) -> Dict:
        t = text.lower()
        if any(x in t for x in ['привет', 'аврора', 'как дела']): return {"intent": "chat", "query": text}
        if any(x in t for x in ['radio', 'радио', 'mix', 'play']): return {"intent": "radio", "query": text}
        return {"intent": "search", "query": text}
