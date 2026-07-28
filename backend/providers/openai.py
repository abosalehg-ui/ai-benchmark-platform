"""مزود OpenAI."""
from __future__ import annotations

import re

from backend.providers.openai_compatible import OpenAICompatibleProvider

# نماذج التفكير من عائلة o (o1/o3/o4…): لا تقبل رسالة system منفصلة،
# ولا temperature، وتستخدم max_completion_tokens بدل max_tokens.
_O_SERIES = re.compile(r"^o\d")


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    available_models = [
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gpt-5-mini",
        "o3",
    ]
    API_URL = "https://api.openai.com/v1/chat/completions"
    DEFAULT_TIMEOUT = 180.0

    @staticmethod
    def _is_o_series(model: str) -> bool:
        return bool(_O_SERIES.match(model))

    def _build_messages(self, prompt, system, model):
        # نماذج o لا تقبل رسالة system، فندمجها في بداية رسالة المستخدم
        if self._is_o_series(model):
            content = f"{system}\n\n{prompt}" if system else prompt
            return [{"role": "user", "content": content}]
        return super()._build_messages(prompt, system, model)

    def _build_body(self, model, messages, max_tokens, temperature):
        # نماذج o ما تقبل temperature ولها max_completion_tokens
        if self._is_o_series(model):
            return {"model": model, "messages": messages, "max_completion_tokens": max_tokens}
        return super()._build_body(model, messages, max_tokens, temperature)
