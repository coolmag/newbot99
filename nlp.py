import logging
from ai_manager import AIManager

logger = logging.getLogger("nlp")

# Create a single, shared instance of the AI Manager
ai_manager = AIManager()

async def analyze_message(text: str):
    """
    Analyzes the user's message to determine intent and query.
    This is now a wrapper around the AIManager's method.
    """
    return await ai_manager.analyze_message(text)