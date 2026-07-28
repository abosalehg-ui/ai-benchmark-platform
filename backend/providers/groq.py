"""مزود Groq - استنتاج سريع للنماذج المفتوحة."""
from __future__ import annotations

from backend.providers.openai_compatible import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    available_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]
    API_URL = "https://api.groq.com/openai/v1/chat/completions"
