"""مزود xAI (نماذج Grok)."""
from __future__ import annotations

from backend.providers.openai_compatible import OpenAICompatibleProvider


class XAIProvider(OpenAICompatibleProvider):
    name = "xai"
    available_models = [
        "grok-4.5",
        "grok-4.3",
    ]
    API_URL = "https://api.x.ai/v1/chat/completions"
    DEFAULT_TIMEOUT = 180.0
