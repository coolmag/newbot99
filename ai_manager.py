import logging
import json
from typing import Optional
import httpx
# 👇 ВАЖНО: Используем новый SDK
from google import genai 
from config import get_settings

logger = logging.getLogger("ai_manager")
settings = get_settings() # Create a single, cached settings instance

class AIManager:
    """
    🧠 AI Manager (2026 Modern SDK).
    Strategies:
    1. OpenRouter Free Models.
    2. Google GenAI (New SDK v1.0+).
    """
    
    def __init__(self):
        self.providers = []
        
        # Настраиваем OpenRouter
        if settings.OPENROUTER_API_KEY:
            self.providers.append("OpenRouter")
            
        # Настраиваем Google GenAI (Новый SDK)
        if settings.GOOGLE_API_KEY:
            try:
                # Инициализация клиента по-новому
                self.gemini_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
                self.providers.append("Gemini")
            except Exception as e:
                logger.error(f"Failed to configure Gemini Client: {e}")

    async def analyze_message(self, text: str) -> dict:
        prompt = f"""
        Analyze this user message for a music bot.
        Message: "{text}"
        
        Return ONLY a JSON object (no markdown) with:
        1. "intent": "radio", "search", or "chat".
        2. "query": clean search term or genre.
        """

        # 1. Пробуем OpenRouter
        if "OpenRouter" in self.providers:
            res = await self._call_openrouter(prompt)
            if res: return res

        # 2. Пробуем Gemini (Новый метод)
        if "Gemini" in self.providers:
            res = await self._call_gemini(prompt)
            if res: return res
            
        return self._regex_fallback(text)

    async def _call_gemini(self, prompt: str) -> Optional[dict]:
        try:
            # Синтаксис нового SDK (2026)
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=prompt
            )
            logger.info("Gemini (direct) succeeded.") # Added this log for consistency
            return self._parse_json(response.text)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return None

    async def _call_openrouter(self, prompt: str) -> Optional[dict]:
        free_models = ["google/gemini-2.0-flash-exp:free", "meta-llama/llama-3.2-3b-instruct:free"]
        headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://railway.app"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            for model in free_models:
                try:
                    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
                    resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                    if resp.status_code == 200:
                        logger.info(f"OpenRouter ({model}) succeeded.") # Added this log for consistency
                        return self._parse_json(resp.json()['choices'][0]['message']['content'])
                except: continue
        return None

    def _regex_fallback(self, text: str) -> dict:
        logger.info("⚠️ AI failed. Using Regex Fallback.")
        text_lower = text.lower()
        radio_keywords = ['радио', 'radio', 'play', 'играй', 'включи', 'mix']
        if any(k in text_lower for k in radio_keywords):
            for k in radio_keywords: text_lower = text_lower.replace(k, '')
            return {"intent": "radio", "query": text_lower.strip() or "top hits"}
        return {"intent": "search", "query": text}

    async def get_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        """Метод для простой болталки"""
        full_prompt = f"{system_prompt}\nUser: {prompt}"
        
        # 1. OpenRouter
        if "OpenRouter" in self.providers:
            # Используем ту же логику, но ожидаем текст, а не JSON
            try:
                headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://railway.app"}
                payload = {
                    "model": "google/gemini-2.0-flash-exp:free", # Или любая другая free
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                    if resp.status_code == 200:
                        return resp.json()['choices'][0]['message']['content']
            except: pass

        # 2. Gemini
        if "Gemini" in self.providers:
            try:
                # Используем chat session для контекста (по желанию) или просто generate
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=full_prompt
                )
                return response.text
            except: pass
            
        return "Извини, я сейчас немного занят музыкой, давай поболтаем позже! 🎧"

    def _parse_json(self, text: str) -> Optional[dict]:
        try:
            cleaned = text.strip().replace("```json", "").replace("```", "")
            return json.loads(cleaned)
        except: return None