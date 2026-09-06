"""حماية من SSRF: التحقّق من عناوين base_url التي يتحكّم بها المستخدم.

المشكلة: `/api/ollama/models?base_url=…` و`targets[].base_url` كانا يُمرَّران
مباشرةً إلى httpx، فيستطيع أي طالب إجبار الخادم على إصدار طلب لأي عنوان —
بما فيه خدمات الشبكة الداخلية وnode metadata (169.254.169.254).

السياسة: http/https فقط، ونرفض العناوين الخاصة/loopback إلا إذا كان المضيف
ضمن allowlist. الافتراضي يسمح بـ localhost فقط (سيناريو Ollama المحلي).
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
_DEFAULT_ALLOWED_HOSTS = "localhost,127.0.0.1,::1,host.docker.internal"


class UnsafeURLError(ValueError):
    """العنوان مرفوض لأسباب أمنية."""


def _allowed_hosts() -> set[str]:
    raw = os.getenv("ALLOWED_UPSTREAM_HOSTS", _DEFAULT_ALLOWED_HOSTS)
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_base_url(url: str, *, resolve: bool = True) -> str:
    """تحقّق من العنوان وارجعه بدون سلاش زائد. يرفع UnsafeURLError عند الرفض.

    المضيفون في ``ALLOWED_UPSTREAM_HOSTS`` معفَون من فحص العناوين الخاصة —
    لأنّ Ollama المحلي هو بالضبط ``127.0.0.1`` وهو استخدام مشروع.

    ``resolve=False`` يفحص كل شيء **عدا** حلّ أسماء المضيفين، فيبقى الاستدعاء
    بلا حجب. يُستخدم في مُتحقِّق Pydantic الذي يعمل داخل حلقة الأحداث؛ الفحص
    الكامل يجري بعده في ``asyncio.to_thread``. العناوين الحرفية (وهي كل ما
    يهمّ في هجوم SSRF النمطي: ``169.254.169.254``، ``127.0.0.1``) تُفحص في
    الحالتين لأنها لا تحتاج DNS أصلاً.
    """
    if not url or not url.strip():
        raise UnsafeURLError("عنوان فارغ")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"مخطّط غير مسموح: {parsed.scheme or '(بلا مخطّط)'} — استخدم http أو https")

    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeURLError("العنوان بلا اسم مضيف")

    allowed = _allowed_hosts()
    if host in allowed:
        return url.strip().rstrip("/")

    # عنوان حرفي: نفحصه مباشرةً بلا أي استدعاء شبكي. كان يمرّ عبر
    # ``getaddrinfo`` بلا داعٍ — نداء نظام كامل لعنوان معروف سلفاً.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_ip(literal):
            raise UnsafeURLError(
                f"العنوان {host} يشير إلى شبكة داخلية ({host}). "
                "أضِفه إلى ALLOWED_UPSTREAM_HOSTS إن كنت تقصد ذلك."
            )
        return url.strip().rstrip("/")

    if not resolve:
        return url.strip().rstrip("/")

    # نحلّ الاسم ونفحص كل العناوين المُرجَعة.
    #
    # حدّ معروف: هذا **لا** يمنع DNS rebinding. نحن نحلّ الاسم للفحص، ثم يحلّه
    # httpx من جديد عند الطلب — من يتحكّم بالـ DNS يستطيع إرجاع عنوان عام في
    # الاستعلام الأوّل و127.0.0.1 في الثاني. الأثر محدود لأن المستخدم هو من
    # يكتب ``base_url`` في أداة محلية، لكن لا تبنِ قرار نشر على أن الفجوة مغلقة:
    # إغلاقها يحتاج تثبيت العنوان المُتحقَّق منه في الاتصال نفسه.
    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeURLError(f"تعذّر حلّ اسم المضيف: {host}") from e

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise UnsafeURLError(
                f"العنوان {host} يشير إلى شبكة داخلية ({addr}). "
                "أضِفه إلى ALLOWED_UPSTREAM_HOSTS إن كنت تقصد ذلك."
            )

    return url.strip().rstrip("/")
