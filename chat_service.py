import logging
from typing import Dict
from ai_manager import AIManager 
from ai_personas import get_system_prompt

logger = logging.getLogger("chat_service")
ai_manager = AIManager() 

class ChatManager:
    # Хранилище состояний: {chat_id: "mode_name"}
    _modes: Dict[int, str] = {}
    _histories: Dict[int, list] = {}

    @classmethod
    def get_mode(cls, chat_id: int) -> str:
        """Возвращает текущий режим чата (по умолчанию 'default')."""
        return cls._modes.get(chat_id, "default")

    @classmethod
    def set_mode(cls, chat_id: int, mode: str):
        """Устанавливает режим личности AI."""
        cls._modes[chat_id] = mode
        logger.info(f"Mode for {chat_id} set to {mode}")

    @staticmethod
    async def get_response(chat_id: int, text: str, user_name: str) -> str:
        mode = ChatManager.get_mode(chat_id)
        system_prompt = get_system_prompt(mode)
        
        # Подмешиваем имя пользователя для персонализации
        full_system_prompt = f"{system_prompt}\n(User's name is {user_name})"
        
        try:
            # Вызываем AI
            response = await ai_manager.get_chat_response(text, system_prompt=full_system_prompt)
            return response
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return "Что-то я потерял нить разговора... 🤯"

# Заглушка для викторины (если используется в handlers.py)
class QuizManager:
    @staticmethod
    def start_quiz(chat_id: int):
        return "Викторина пока в разработке! 🔧"