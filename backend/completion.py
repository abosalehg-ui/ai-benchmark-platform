"""استدعاء نموذج عبر الـ cache المشترك.

كانت هذه الدالة تعيش داخل ``runner.py`` وتغلّف النموذج المستهدف وحده، فاستدعاءات
الحَكَم في ``llm_judge`` كانت تدفع تكلفتها كاملةً في كل إعادة تشغيل رغم أن
المستخدم مفعّل الـ cache. نقلها إلى وحدة محايدة يجعل المسارين يتشاركان نفس
الـ cache بلا استيراد دائري — ``llm_judge`` لا يستطيع استيراد ``runner`` لأن
``runner`` يستورد البنشماركات.

كتابات وقراءات SQLite تمرّ عبر ``asyncio.to_thread``: هذه الدالة تُستدعى من داخل
حلقة الأحداث أثناء بثّ SQL، وأي استدعاء متزامن يجمّد البثّ لبقيّة النماذج.
"""
from __future__ import annotations

import asyncio

from backend import db
from backend.providers.base import BaseProvider, ModelResponse


async def complete_with_cache(
    provider: BaseProvider,
    *,
    prompt: str,
    model: str,
    system: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
    use_cache: bool = True,
) -> tuple[ModelResponse, bool]:
    """ينفّذ الاستدعاء عبر الـ cache إن كان مفعّلاً. يرجع ``(response, cache_hit)``."""
    async def _call() -> ModelResponse:
        return await provider.complete(
            prompt=prompt, model=model, max_tokens=max_tokens,
            temperature=temperature, system=system,
        )

    if not use_cache:
        return await _call(), False

    key = db.make_cache_key(provider.name, model, prompt, system, temperature, max_tokens)
    cached = await asyncio.to_thread(db.cache_get, key)
    if cached:
        return ModelResponse(
            text=cached["response_text"],
            input_tokens=cached["input_tokens"],
            output_tokens=cached["output_tokens"],
            latency_ms=0.0,  # cache hit = صفر
            cost_usd=0.0,    # cache hit = صفر دولار
            model_id=model,
        ), True

    resp = await _call()
    if not resp.is_error and resp.text:
        await asyncio.to_thread(
            db.cache_put, key, provider.name, model,
            text=resp.text, input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens, cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
        )
    return resp, False
