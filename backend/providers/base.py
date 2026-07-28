"""واجهة موحدة لجميع مزودي نماذج الذكاء الاصطناعي."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.logging_config import get_logger, redact

logger = get_logger(__name__)


def format_http_error(provider: str, model: str, exc: httpx.HTTPStatusError) -> str:
    """يسجّل الخطأ كاملاً خادمياً ويرجع رسالة مختصرة ومنقّحة للعميل.

    أجسام أخطاء المزوّدين قد تحوي معرّفات تنظيمية أو أجزاءً من المفتاح،
    وكانت تُعاد للعميل حرفياً (200 حرف). الآن التفاصيل في اللوج فقط.
    """
    status = exc.response.status_code
    body = redact(exc.response.text[:500])
    logger.warning("%s/%s: HTTP %s — %s", provider, model, status, body)
    hints = {
        401: "مفتاح API غير صالح أو منتهي",
        403: "المفتاح لا يملك صلاحية لهذا النموذج",
        404: "النموذج غير موجود لدى المزوّد",
        429: "تجاوزت حدّ المعدّل (rate limit) — جرّب لاحقاً",
    }
    hint = hints.get(status, "خطأ من المزوّد")
    return f"HTTP {status}: {hint}"


def format_exception(provider: str, model: str, exc: Exception) -> str:
    """يسجّل استثناءً غير متوقّع ويرجع نصاً منقّحاً."""
    logger.exception("%s/%s: فشل الاستدعاء", provider, model)
    return redact(f"{type(exc).__name__}: {exc}")


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


def estimate_tokens_from_text(text: str) -> int:
    """تقدير تقريبي لعدد التوكنات من النص.

    قاعدة عامة: ~3.5 حرف/توكن للإنجليزية، ~2 حرف/توكن للعربية.
    نستخدم 3 كمعدّل وسط محافظ.
    """
    if not text:
        return 0
    return max(1, len(text) // 3)


def measure_latency():
    """Context manager لقياس زمن الاستجابة."""
    return _LatencyTimer()


class _LatencyTimer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000
