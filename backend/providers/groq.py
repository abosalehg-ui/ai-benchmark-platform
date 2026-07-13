"""مزود Groq - استنتاج سريع للنماذج المفتوحة."""
from __future__ import annotations

from backend.providers.openai_compatible import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    available_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
        "deepseek-r1-distill-llama-70b",
    ]
    API_URL = "https://api.groq.com/openai/v1/chat/completions"
