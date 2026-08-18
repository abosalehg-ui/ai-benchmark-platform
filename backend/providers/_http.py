"""HTTP helper مشترك: عميل مُعاد الاستخدام + retry وbackoff لكل المزوّدين.

كان كل استدعاء يُنشئ ``httpx.AsyncClient`` جديداً ويُدمّره. تشغيل 200 مسألة ×
5 نماذج = ألف مصافحة TLS كاملة لمضيفين قليلين ثابتين — عشرات الثواني مهدورة،
وأسوأ: المصافحة تُحسب داخل ``latency_ms`` فتلوّث القياس الذي تنتجه المنصّة
نفسها. العميل المشترك يعيد استخدام الاتصالات (keep-alive) فيقيس الزمن النموذجَ
لا الشبكة.

العميل مفهرَس بحلقة الأحداث: كائنات httpx مرتبطة بالحلقة التي أُنشئت فيها،
وحلقة أخرى (اختبار يستدعي ``asyncio.run`` مرّتين) تحتاج عميلها.

المهلة تُمرَّر **لكل طلب** لا للعميل: Ollama المحلي يحتاج 300 ثانية بينما
OpenAI يحتاج 180، ولا يصحّ أن يرث أحدهما مهلة الآخر.
"""
from __future__ import annotations

import asyncio
import os
import random

import httpx

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0

_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


async def get_http_client() -> httpx.AsyncClient:
    """العميل المشترك لحلقة الأحداث الحالية — يُنشأ عند أوّل استخدام."""
    loop = asyncio.get_running_loop()
    # نظّف حلقات انتهت حتى لا ينمو القاموس في عمليات طويلة
    for dead in [ev for ev in _clients if ev.is_closed()]:
        _clients.pop(dead, None)

    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=_env_int("HTTP_MAX_CONNECTIONS", 64),
                max_keepalive_connections=_env_int("HTTP_MAX_KEEPALIVE", 32),
            )
        )
        _clients[loop] = client
    return client


async def close_http_client() -> None:
    """يُغلق عميل الحلقة الحالية. يُستدعى من ``lifespan`` عند إيقاف الخادم."""
    loop = asyncio.get_running_loop()
    client = _clients.pop(loop, None)
    if client is not None and not client.is_closed:
        await client.aclose()


async def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict | None,
    json: dict | None,
    timeout: float,
    max_retries: int,
    base_delay: float,
) -> httpx.Response:
    """جسم مشترك لـ GET/POST: نفس سياسة إعادة المحاولة لكليهما."""
    client = await get_http_client()
    kwargs: dict = {"headers": headers, "timeout": timeout}
    if json is not None:
        kwargs["json"] = json

    for attempt in range(max_retries + 1):
        try:
            r = await client.request(method, url, **kwargs)
            if r.status_code in RETRY_STATUS and attempt < max_retries:
                await _sleep_backoff(attempt, base_delay, r)
                continue
            r.raise_for_status()
            return r
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout):
            if attempt < max_retries:
                await _sleep_backoff(attempt, base_delay)
                continue
            raise
        except httpx.HTTPStatusError:
            raise
    raise RuntimeError(f"{method} {url}: انتهت المحاولات بدون استجابة")


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
    return await _request_with_retry(
        "POST", url, headers=headers, json=json,
        timeout=timeout, max_retries=max_retries, base_delay=base_delay,
    )


async def get_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 30.0,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> httpx.Response:
    """GET عبر نفس العميل المشترك (يستخدمه Ollama لجلب النماذج المحلية)."""
    return await _request_with_retry(
        "GET", url, headers=headers, json=None,
        timeout=timeout, max_retries=max_retries, base_delay=base_delay,
    )


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
