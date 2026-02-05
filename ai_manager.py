import logging
import json
import re
from google import genai
from typing import Optional, Dict

from config import get_settings

logger = logging.getLogger("ai_manager")

AURORA_SYSTEM_PROMPT = """
Ты — Аврора, ИИ-диджей в Телеграм-боте.
Твой стиль: дерзкая, веселая, используешь эмодзи (🎧, 🛸, 🎸).
Ты не ассистент, ты — фанатка музыки.
Отвечай кратко (до 2 предложений), если не просят длинно.
"""

class AIManager:
    """
    🧠 AI Manager (Client SDK Edition).
    """
    
    def __init__(self):
        logger.info("--- Running AIManager Version 5.0 (Client SDK Refactor) ---")
        self.is_active = False
        self.client = None
        self.model_name = 'gemma-3-12b-it'
        
        settings = get_settings()
        api_key = settings.GOOGLE_API_KEY
        
        if api_key:
            try:
                # New SDK: Instantiate a client
                self.client = genai.Client(api_key=api_key)
                # Test the connection by getting the model info (optional but good practice)
                self.client.models.get(model=self.model_name)
                self.is_active = True
                logger.info(f"✅ Google GenAI client configured successfully for model {self.model_name}.")
            except Exception as e:
                logger.error(f"❌ Failed to configure Google GenAI client: {e}")
        else:
            logger.warning("⚠️ GOOGLE_API_KEY is missing!")

    async def analyze_message(self, text: str) -> Dict:
        if not self.is_active:
            return self._regex_fallback(text)
            
        try:
            prompt = f"""
            Classify intent:
            1. 'search' (specific song/artist)
            2. 'radio' (genre/mood/vibe/mix/hits)
            3. 'chat' (general conversation)
            
            Format: INTENT: <intent> | QUERY: <query>
            
            Input: "{text}"
            """

            # New SDK: Use client.models.generate_content and pass config as a dict
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    'temperature': 0.1
                }
            )
            
            raw_text = response.text.strip()

            intent = "chat"
            query = text

            if "INTENT:" in raw_text:
                if "search" in raw_text: intent = "search"
                elif "radio" in raw_text: intent = "radio"
                
                if "| QUERY:" in raw_text:
                    query = raw_text.split("| QUERY:")[1].strip()
            
            return {"intent": intent, "query": query}

        except Exception as e:
            logger.warning(f"[NLP] Error: {e}, using regex fallback.")
            return self._regex_fallback(text)

    async def get_chat_response(self, user_text: str, system_prompt: str = "") -> str:
        if not self.is_active: return "Мозг отключен 🔌"

        final_system_prompt = system_prompt or AURORA_SYSTEM_PROMPT

        try:
            # New SDK: Use client.chats.create
            chat = self.client.chats.create(
                model=self.model_name,
                history=[
                    {
                        "role": "user",
                        "parts": [final_system_prompt + "\n\nТы поняла свою роль?"]
                    },
                    {
                        "role": "model",
                        "parts": ["Конечно! Я Аврора, твой музыкальный пилот! Погнали! 🎧🛸"]
                    }
                ]
            )
            
            # New SDK: Use chat.send_message_async
            response = await chat.send_message_async(user_text)
            return response.text
            
        except Exception as e:
            logger.error(f"AI ERROR: {e}")
            return "Антенна погнулась... 🛸 (Сбой нейросети)"

    def _regex_fallback(self, text: str) -> Dict:
        text_lower = text.lower()
        if any(k in text_lower for k in ['привет', 'как дела', 'кто ты']):
             return {"intent": "chat", "query": text}

        if any(k in text_lower for k in ['радио', 'radio', 'play', 'играй']):
            return {"intent": "radio", "query": text}
            
        return {"intent": "search", "query": text}