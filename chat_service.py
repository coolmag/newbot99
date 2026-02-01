import logging
from ai_manager import AIManager 
from ai_personas import get_system_prompt

logger = logging.getLogger("chat_service")
ai_manager = AIManager() 

class ChatManager:
    """
    Только генерация ответов. Состояние хранится в Telegram Context.
    """
    @staticmethod
    async def get_response(text: str, user_name: str, mode: str = "default") -> str:
        # Получаем промпт для конкретного режима
        system_prompt = get_system_prompt(mode)
        full_prompt = f"{system_prompt}\n(User name: {user_name})"
        
        try:
            # Gemma 3 / Gemini
            return await ai_manager.get_chat_response(text, system_prompt=full_prompt)
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return "Что-то с памятью моей... 🤯"