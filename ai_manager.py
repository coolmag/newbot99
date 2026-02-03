import logging
import json
import asyncio
import re
import google.generativeai as genai
from typing import Optional, Dict

from config import get_settings

logger = logging.getLogger("ai_manager")

# ВАЖНО: Gemma требует настройки генерации, иначе может выдавать пустые ответы
# Этот импорт был причиной предыдущих падений, теперь он на месте.
try:
    from google.generativeai.types import GenerationConfig
except ImportError:
    # Фоллбэк для разных версий, если types не существует
    GenerationConfig = genai.GenerationConfig

# Промпт, задающий личность Авроры
AURORA_SYSTEM_PROMPT = """
Ты — Аврора, ИИ-диджей в Телеграм-боте.
Твой стиль: дерзкая, веселая, используешь эмодзи (🎧, 🛸, 🎸).
Ты не ассистент, ты — фанатка музыки.
Отвечай кратко (до 2 предложений), если не просят длинно.
"""

class AIManager:
    """
    🧠 AI Manager (Gemma "Jailbreak" Edition).
    Применен обходной путь для注入личности в Gemma через историю чата.
    """
    
    def __init__(self):
        self.is_active = False
        settings = get_settings()
        api_key = settings.GOOGLE_API_KEY
        
        if api_key:
            try:
                genai.configure(api_key=api_key)
                # Инициализируем модель "чистой", без system_instruction, чтобы избежать ошибки 400
                self.model = genai.GenerativeModel('gemma-3-12b-it') 
                self.is_active = True
                logger.info("✅ Google GenAI configured successfully (Gemma 3).")
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
        
        # Используем gemma-3-4b-it для скорости и экономии
        model = genai.GenerativeModel("gemma-3-4b-it")
        generation_config = GenerationConfig(response_mime_type="application/json")
        
        try:
            response = await model.generate_content_async(
                contents=prompt,
                generation_config=generation_config
            )
            data = self._parse_json(response.text)
            if data and data.get("intent"):
                logger.info(f"🤖 AI (gemma-3-4b-it): {data}")
                return data
        except Exception as e:
            logger.warning(f"⚠️ NLP model error: {e}. Trying regex fallback...")

        return self._regex_fallback(text)

    async def get_chat_response(self, user_text: str, system_prompt: str = "") -> str:
        if not self.is_active: return "Мозг отключен 🔌"

        # Используем основной системный промпт, если не передан кастомный
        final_system_prompt = system_prompt or AURORA_SYSTEM_PROMPT

        try:
            # Создаем чат с "фейковой" историей (Jailbreak личности для Gemma)
            chat = self.model.start_chat(history=[
                {
                    "role": "user",
                    "parts": [final_system_prompt + "\n\nТы поняла свою роль?"]
                },
                {
                    "role": "model",
                    "parts": ["Конечно! Я Аврора, твой музыкальный пилот! Погнали! 🎧🛸"]
                }
            ])
            
            # Отправляем реальное сообщение
            response = await chat.send_message_async(user_text)
            return response.text
            
        except Exception as e:
            # Логируем точную ошибку
            logger.error(f"CRITICAL AI ERROR: {e}")
            return "Антенна погнулась... 🛸 (Сбой нейросети)"

    def _regex_fallback(self, text: str) -> Dict:
        # ... (regex fallback остался без изменений)
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
        # ... (json parser остался без изменений)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try: return json.loads(match.group(0))
                except: return None
            return None