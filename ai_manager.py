import logging
import json
import asyncio
import re
from typing import Optional, List
from google import genai
from config import get_settings

logger = logging.getLogger("ai_manager")
settings = get_settings()

class AIManager:
    """
    🧠 AI Manager (Context Aware).
    Target: Gemma 3 (12B-it).
    Features: Short-term memory & strict intent classification.
    """
    
    def __init__(self):
        self.client = None
        self.is_active = False
        # Простая память: {chat_id: [msg1, msg2]}
        self.history = {} 
        
        api_key = settings.GOOGLE_API_KEY
        if api_key:
            try:
                self.client = genai.Client(api_key=api_key)
                self.is_active = True
                logger.info("✅ Gemma 3 Connected.")
            except Exception as e:
                logger.error(f"❌ Failed to init AI: {e}")

    async def analyze_message(self, text: str) -> dict:
        """Определяем намерение: Музыка или Чат?"""
        if not self.is_active: return self._regex_fallback(text)

        # Промпт стал строже
        prompt = f"""
        Classify user message for a Music Bot.
        Input: "{text}"
        
        Rules:
        1. "radio": user asks to play genre, mood, playlist, 'something like...', 'mix'.
        2. "search": user asks for specific song/artist name.
        3. "chat": user says hello, asks questions, talks about life, or gives feedback.
        
        Output JSON ONLY:
        {{"intent": "radio"|"search"|"chat", "query": "search term or null"}}
        """

        model = "gemma-3-12b-it" 
        
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=model,
                contents=prompt
            )
            if response.text:
                return self._parse_json(response.text) or self._regex_fallback(text)
        except Exception as e:
            logger.warning(f"AI Analysis Error: {e}")
            
        return self._regex_fallback(text)

    async def get_chat_response(self, text: str, user_name: str, system_prompt: str = "") -> str:
        """Генерация ответа с учетом контекста"""
        if not self.is_active: return "Мозг оффлайн 🔌"

        # Формируем контекст (последние сообщения)
        # В реальном проекте тут нужен chat_id, но пока упростим
        context = f"System: {system_prompt}\nUser ({user_name}): {text}"
        
        model = "gemma-3-12b-it"

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=model,
                contents=context
            )
            
            answer = response.text
            if not answer or len(answer) < 2:
                return "..."
            
            # Убираем кавычки, если модель их добавила
            return answer.strip('"')
            
        except Exception as e:
            logger.error(f"Chat Gen Error: {e}")
            return "Связь прервалась..."

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
