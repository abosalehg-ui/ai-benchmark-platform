"""رؤوس أمنية + مصادقة اختيارية برمز مشترك.

المنصّة كانت بلا أي رأس أمني وبلا مصادقة على 14 endpoint — منها عمليات
هدّامة (`DELETE /api/runs/{id}`). هنا طبقتان خفيفتان:

1. ``SecurityHeadersMiddleware``: CSP يمنع أي مصدر خارجي (كل الأصول
   مستضافة محلياً في ``frontend/vendor/``)، مع nosniff و frame-ancestors.
2. ``require_api_token``: dependency تُفعَّل تلقائياً فقط حين يُضبَط
   ``API_TOKEN`` — فالتشغيل المحلي يبقى بلا احتكاك، والنشر يصبح ممكناً.
"""
from __future__ import annotations

import hmac
import ipaddress
import os

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

# 'unsafe-inline' للأنماط فقط: بعض العناصر تُضبط style سطرياً (شريط التقدّم،
# شدّة لون خلايا H2H). السكربتات بلا unsafe-inline — وهو ما يهمّ ضد XSS.
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "object-src 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), interest-cohort=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """يضيف رؤوس الأمان لكل استجابة."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


def api_token_configured() -> bool:
    return bool(os.getenv("API_TOKEN", "").strip())


def _is_local_client(host: str) -> bool:
    """هل الطلب قادم من نفس الجهاز؟"""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def network_access_allowed() -> bool:
    """صمّام لمن يقصد فعلاً فتح المنصّة على الشبكة بلا رمز."""
    return os.getenv("ALLOW_UNAUTHENTICATED_NETWORK", "").strip().lower() in {"1", "true", "yes"}


async def require_api_token(request: Request) -> None:
    """يفرض ``X-API-Token`` — لكن فقط إذا ضُبِط ``API_TOKEN`` في البيئة.

    بلا ``API_TOKEN`` تعمل المنصّة كما كانت (أداة محلية بلا احتكاك).
    مع ضبطه تصبح كل مسارات ``/api`` محميّة، فيمكن نشرها خلف الشبكة.
    """
    expected = os.getenv("API_TOKEN", "").strip()
    if not expected:
        # بلا رمز، المنصّة أداة محلية بلا احتكاك — لكن ``uvicorn --host 0.0.0.0``
        # سطرٌ واحد، وبعده يستطيع أي جهاز في الشبكة حذف السجل عبر
        # ``DELETE /api/runs/{id}``، وتعبر مفاتيح المستخدم في جسم ``/api/run``
        # نصّاً صريحاً. CORS يمنع صفحات المتصفّح لا ``curl``.
        #
        # حدّ معروف: خلف عاكس (reverse proxy) على نفس الجهاز يصل كل طلب من
        # 127.0.0.1 فيمرّ هذا الفحص — النشر خلف عاكس يحتاج API_TOKEN فعلاً.
        client_host = request.client.host if request.client else ""
        if _is_local_client(client_host) or network_access_allowed():
            return
        raise HTTPException(
            401,
            "المنصّة مفتوحة بلا مصادقة وهذا الطلب قادم من خارج الجهاز. "
            "اضبط API_TOKEN في بيئة الخادم (وأدخله في تبويب «المفاتيح»)، "
            "أو ALLOW_UNAUTHENTICATED_NETWORK=1 إن كنت تقصد فتحها للشبكة.",
        )
    supplied = request.headers.get("X-API-Token", "")
    # مقارنة ثابتة الزمن — لا نسرّب طول الرمز عبر توقيت الردّ
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "رمز وصول غير صالح أو مفقود (X-API-Token)")


def sanitize_csv_cell(value) -> str:
    """يمنع حقن الصيغ في Excel/LibreOffice.

    التصدير يضيف BOM لتشجيع فتح الملف في Excel، وردود النماذج قد تبدأ بـ
    ``=`` أو ``+`` أو ``-`` أو ``@`` فيفسّرها كصيغة قابلة للتنفيذ.
    """
    if value is None:
        return ""
    text = str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text
