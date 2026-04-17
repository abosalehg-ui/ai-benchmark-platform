"""سجل مزودي النماذج."""
from __future__ import annotations

from backend.providers.base import BaseProvider, ModelResponse
from backend.providers.claude import ClaudeProvider
from backend.providers.gemini import GeminiProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.openai import OpenAIProvider
from backend.providers.openrouter import OpenRouterProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    "anthropic": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
}


def make_provider(provider_name: str, api_key: str = "", base_url: str | None = None) -> BaseProvider:
    """أنشئ نسخة من المزود المطلوب."""
    if provider_name not in PROVIDERS:
        raise ValueError(f"مزود غير معروف: {provider_name}")
    cls = PROVIDERS[provider_name]
    if provider_name == "ollama":
        return cls(api_key=api_key, base_url=base_url or "http://localhost:11434")
    return cls(api_key=api_key, base_url=base_url)


__all__ = ["BaseProvider", "ModelResponse", "PROVIDERS", "make_provider"]
