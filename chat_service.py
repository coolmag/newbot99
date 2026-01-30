import logging
from typing import Dict
from ai_manager import AIManager 
from ai_personas import get_system_prompt

logger = logging.getLogger("chat_service")
ai_manager = AIManager() 

class ChatManager:
    _modes: Dict[int, str] = {}

    @classmethod
    def get_mode(cls, chat_id: int) -> str:
        return cls._modes.get(chat_id, "default")

    @classmethod
    def set_mode(cls, chat_id: int, mode: str):
        cls._modes[chat_id] = mode

    @staticmethod
    async def get_response(chat_id: int, text: str, user_name: str) -> str:
        mode = ChatManager.get_mode(chat_id)
        system_prompt = get_system_prompt(mode)
        full_system_prompt = f"{system_prompt}\n(User: {user_name})"
        
        try:
            return await ai_manager.get_chat_response(text, system_prompt=full_system_prompt)
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return "Что-то я потерял нить разговора... 🤯"

class QuizManager:
    @staticmethod
    def start_quiz(chat_id: int):
        return "Викторина пока в разработке! 🔧"

