import logging
from ai_manager import AIManager 
from ai_personas import get_system_prompt

logger = logging.getLogger("chat_service")
ai_manager = AIManager() 

class ChatManager:
    """
    Генерация ответов с учетом контекста.
    """
    @staticmethod
    async def get_response(text: str, user_name: str, mode: str = "default") -> str:
        system_prompt = get_system_prompt(mode)
        
        try:
            # ИСПРАВЛЕНО: Передаем user_name вторым аргументом
            return await ai_manager.get_chat_response(text, user_name, system_prompt=system_prompt)
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return "Что-то нейросети сегодня штормит... 🤯"

class QuizManager:
    @staticmethod
    def start_quiz(chat_id: int):
        return "Викторина пока в разработке! 🔧"
