import logging
from google import genai

from ai_manager import AIManager # Теперь это класс

logger = logging.getLogger("nlp")

# Инициализируем AI менеджер глобально
ai_manager = AIManager()

async def analyze_message(text: str):
    try:
        # Промпт v4: Разделение на Search (Трек) и Radio (Поток)
        prompt = f"""
        Ты — мозг музыкального бота. Твоя задача — классифицировать запрос юзера.
        
        ДОСТУПНЫЕ ИНТЕНТЫ:
        1. INTENT: search
           Использовать ТОЛЬКО если юзер называет КОНКРЕТНОГО исполнителя или название песни.
           Пример: "Включи Linkin Park", "Поставь Numb", "Скриптонит", "Eminem".
           
        2. INTENT: radio
           Использовать, если юзер просит:
           - Жанр (рок, поп, рэп, джаз)
           - Настроение (веселое, грустное, для сна, драйвовое, расслабиться)
           - Подборку ("хиты", "новинки", "топ чарт", "русские хиты")
           - Абстрактное ("включи что-то", "хочу музыки", "волну", "посоветуй", "наяривай")
           
        3. INTENT: chat
           Только для "Привет", "Как дела", "Кто ты" и болтовни не о музыке.
        
        ФОРМАТ ОТВЕТА (Строго одна строка):
        INTENT: <intent> | QUERY: <поисковый запрос>
        
        Примеры:
        User: "Привет" -> INTENT: chat | QUERY: Привет
        User: "Linkin Park Numb" -> INTENT: search | QUERY: Linkin Park Numb
        User: "Включи трек Федерико Феллини" -> INTENT: search | QUERY: Galibri & Mavik Федерико Феллини
        
        User: "Хочу что-то веселое" -> INTENT: radio | QUERY: веселая танцевальная музыка
        User: "Врубай рок" -> INTENT: radio | QUERY: best rock music mix
        User: "Русские хиты" -> INTENT: radio | QUERY: русские хиты новинки
        User: "Включи волну попсы" -> INTENT: radio | QUERY: pop music hits
        User: "Для сна" -> INTENT: radio | QUERY: ambient sleep music
        
        User input: "{text}"
        Answer:
        """

        response = await ai_manager.model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.1)
        )
        
        raw_text = response.text.strip()
        logger.info(f"[NLP] Raw AI response: {raw_text}")

        # Парсинг
        intent = "chat"
        query = text

        if "INTENT:" in raw_text:
            if "INTENT: search" in raw_text: intent = "search"
            elif "INTENT: radio" in raw_text: intent = "radio" # <--- НОВЫЙ ИНТЕНТ
            elif "INTENT: chat" in raw_text: intent = "chat"
            
            if "| QUERY:" in raw_text:
                query = raw_text.split("| QUERY:")[1].strip()
        
        return {"intent": intent, "query": query}

    except Exception as e:
        logger.warning(f"[NLP] Error: {e}, regex fallback.")
        return {"intent": "chat", "query": text}
