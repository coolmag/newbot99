import logging
from ai_manager import AIManager 

logger = logging.getLogger("chat_service")

# Инициализируем (или используем тот же инстанс, если хочешь синглтон)
ai_manager = AIManager() 

class ChatManager:
    # Храним историю диалогов (упрощенно)
    histories = {} 

    @staticmethod
    async def get_response(chat_id: int, text: str, user_name: str) -> str:
        system_prompt = f"Ты веселый музыкальный бот Дискжокей. Твой собеседник: {user_name}. Отвечай кратко, с эмодзи. Ты любишь музыку."
        
        try:
            # Вызываем новый метод
            response = await ai_manager.get_chat_response(text, system_prompt=system_prompt)
            return response
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return "Что-то я потерял нить разговора... 🤯"
