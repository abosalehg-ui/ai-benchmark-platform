"""HTTP helper مشترك: retry + backoff لكل المزوّدين."""
from __future__ import annotations

import asyncio
import random

import httpx

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0


async def post_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    json: dict | None = None,
    timeout: float = 120.0,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> httpx.Response:
    """POST مع retry تصاعدي للأخطاء العابرة (5xx، 429، شبكة)."""
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries + 1):
            try:
                r = await client.post(url, headers=headers, json=json)
                if r.status_code in RETRY_STATUS and attempt < max_retries:
                    await _sleep_backoff(attempt, base_delay, r)
                    continue
                r.raise_for_status()
                return r
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                last_exc = e
                if attempt < max_retries:
                    await _sleep_backoff(attempt, base_delay)
                    continue
                raise
            except httpx.HTTPStatusError:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("post_with_retry انتهى بدون استجابة")


async def _sleep_backoff(attempt: int, base: float, response: httpx.Response | None = None) -> None:
    """نوم تصاعدي مع jitter. يحترم Retry-After إذا موجود."""
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                await asyncio.sleep(min(float(retry_after), 30.0))
                return
            except ValueError:
                pass
    delay = min(base * (2 ** attempt) + random.uniform(0, base * 0.5), 30.0)
    await asyncio.sleep(delay)
