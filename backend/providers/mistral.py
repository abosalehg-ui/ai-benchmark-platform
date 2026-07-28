"""مزود Mistral AI."""
from __future__ import annotations

from backend.providers.openai_compatible import OpenAICompatibleProvider


class MistralProvider(OpenAICompatibleProvider):
    name = "mistral"
    available_models = [
        "mistral-large-latest",
        "mistral-medium-latest",
        "mistral-small-latest",
        "codestral-latest",
        "ministral-8b-latest",
    ]
    API_URL = "https://api.mistral.ai/v1/chat/completions"
    DEFAULT_TIMEOUT = 180.0
