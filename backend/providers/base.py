"""واجهة موحدة لجميع مزودي نماذج الذكاء الاصطناعي."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelResponse:
    """استجابة موحدة من أي نموذج."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    model_id: str = ""
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.error is not None


class BaseProvider(ABC):
    """واجهة أساسية لكل مزود."""

    name: str = "base"
    available_models: list[str] = []

    def __init__(self, api_key: str, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> ModelResponse:
        """تنفيذ طلب إكمال على النموذج."""
        ...

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """تقدير التكلفة بالدولار."""
        from backend.pricing import get_price

        price = get_price(self.name, model)
        if not price:
            return 0.0
        return (input_tokens / 1_000_000) * price["input"] + (
            output_tokens / 1_000_000
        ) * price["output"]


def measure_latency():
    """Context manager لقياس زمن الاستجابة."""
    return _LatencyTimer()


class _LatencyTimer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000
