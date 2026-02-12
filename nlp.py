import logging
from ai_manager import ai_instance as ai_manager

logger = logging.getLogger("nlp")

async def analyze_message(text: str, mode: str = "default"):
    """
    Analyzes the user's message to determine intent and query.
    This is now a wrapper around the AIManager's method.
    """
    return await ai_manager.analyze_message(text, mode)