"""مزود OpenAI."""
from __future__ import annotations

from backend.providers.openai_compatible import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    available_models = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "o1-preview",
        "o1-mini",
    ]
    API_URL = "https://api.openai.com/v1/chat/completions"
    DEFAULT_TIMEOUT = 180.0

    @staticmethod
    def _is_o1(model: str) -> bool:
        return model.startswith("o1")

    def _build_messages(self, prompt, system, model):
        # موديلات o1 لا تقبل رسالة system، فندمجها في بداية رسالة المستخدم
        if self._is_o1(model):
            content = f"{system}\n\n{prompt}" if system else prompt
            return [{"role": "user", "content": content}]
        return super()._build_messages(prompt, system, model)

    def _build_body(self, model, messages, max_tokens, temperature):
        # موديلات o1 ما تقبل temperature ولها max_completion_tokens
        if self._is_o1(model):
            return {"model": model, "messages": messages, "max_completion_tokens": max_tokens}
        return super()._build_body(model, messages, max_tokens, temperature)
