import logging
import google.generativeai as genai
try:
    from google.generativeai.types import GenerationConfig
except ImportError:
    GenerationConfig = genai.GenerationConfig

from ai_manager import AIManager # Теперь это класс

logger = logging.getLogger("nlp")

# Инициализируем AI менеджер глобально
ai_manager = AIManager()

async def analyze_message(text: str) -> dict:
    """
    Определяет намерение пользователя: radio, search или chat.
    """
    logger.info(f"[NLP] Analyzing with AI: '{text}'")
    
    try:
        # Используем новый метод экземпляра класса
        result = await ai_manager.analyze_message(text)
        
        if result and result.get("intent"):
            logger.info(f"[NLP] AI result: intent={result['intent']}, query='{result.get('query')}'")
            return result
            
    except Exception as e:
        logger.warning(f"[NLP] AI Error: {e}, falling back to simple patterns.")

    # Фолбэк (если AI сломался внутри)
    return ai_manager._regex_fallback(text)
