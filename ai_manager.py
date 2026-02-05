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

    async def analyze_message(self, text: str, mode: str = "default") -> Dict:
        if not self.is_active:
            return self._regex_fallback(text)

        # Get the persona prompt
        from ai_personas import get_system_prompt
        system_prompt = get_system_prompt(mode)
            
        try:
            prompt = f"""
            {system_prompt}

            Твоя задача — классифицировать запрос юзера и ДАТЬ КОРОТКИЙ КОММЕНТАРИЙ в своем стиле.

            ИНТЕНТЫ:
            1. 'search': Если юзер ищет конкретный трек/исполнителя.
            2. 'radio': Если юзер просит жанр, настроение, подборку или что-то абстрактное.
            3. 'chat': Для болтовни не о музыке.

            ФОРМАТ ОТВЕТА (Строго! Одна строка, три части):
            INTENT: <intent> | QUERY: <query> | COMMENT: <твой комментарий>
            
            Примеры:
            User: "Врубай рок" -> INTENT: radio | QUERY: best rock music mix | COMMENT: О да, сейчас будет жарко! 🎸
            User: "Linkin Park Numb" -> INTENT: search | QUERY: Linkin Park Numb | COMMENT: Легендарный трек! Включаю.
            User: "Привет" -> INTENT: chat | QUERY: Привет | COMMENT: Привет! Какую волну поймаем сегодня?

            User input: "{text}"
            Answer:
            """

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={'temperature': 0.5}
            )
            
            raw_text = response.text.strip()
            logger.info(f"[NLP] Raw AI response for parsing: '{raw_text}'")

            # Default values
            intent = "chat"
            query = text
            comment = None

            # Regex to robustly parse the output
            intent_match = re.search(r"INTENT:\s*(\w+)", raw_text, re.IGNORECASE)
            query_match = re.search(r"QUERY:\s*(.+?)(?=\s*\||\s*$)", raw_text, re.IGNORECASE)
            comment_match = re.search(r"COMMENT:\s*(.+)", raw_text, re.IGNORECASE)

            if intent_match:
                parsed_intent = intent_match.group(1).lower()
                if parsed_intent in ["search", "radio", "chat"]:
                    intent = parsed_intent

            if query_match:
                query = query_match.group(1).strip()
            
            if comment_match:
                comment = comment_match.group(1).strip()
            
            logger.info(f"[NLP] Parsed -> Intent: {intent}, Query: {query}, Comment: {comment}")
            return {"intent": intent, "query": query, "comment": comment}

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
                        "parts": [{"text": final_system_prompt + "\n\nТы поняла свою роль?"}]
                    },
                    {
                        "role": "model",
                        "parts": [{"text": "Конечно! Я Аврора, твой музыкальный пилот! Погнали! 🎧🛸"}]
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