"""إعداد التسجيل (logging) مع تنقيح الأسرار.

كان المشروع بلا أي logging، فأي عطل في الإنتاج يمرّ بلا أثر. هذه الوحدة
تُهيّئ التسجيل مرّة واحدة عند الإقلاع، وتضيف فلتراً يمسح المفاتيح من أي
رسالة قبل كتابتها — حتى لو سُجِّل جسم طلب كامل بالخطأ.
"""
from __future__ import annotations

import logging
import os
import re

# أنماط المفاتيح الشائعة لكل مزوّد + أي حقل اسمه api_key في JSON/dict
_SECRET_PATTERNS = [
    re.compile(r'("?api[_-]?key"?\s*[:=]\s*"?)([^\s,"}\']+)', re.IGNORECASE),
    re.compile(r"\b(sk-ant-)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b(sk-or-v?1-)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b(sk-)[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(gsk_)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b(xai-)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b(AIza)[A-Za-z0-9_\-]{20,}"),
]

_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """امسح أي مفتاح يظهر في النص. يُستخدم أيضاً قبل إرجاع أخطاء للعميل."""
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 2:
            out = pat.sub(lambda m: m.group(1) + _REDACTED, out)
        else:
            out = pat.sub(lambda m: m.group(1) + _REDACTED, out)
    return out


class RedactingFilter(logging.Filter):
    """يمسح الأسرار من الرسالة والوسائط قبل كتابتها في اللوج."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact(v) if isinstance(v, str) else v
                               for k, v in record.args.items()}
            else:
                record.args = tuple(
                    redact(a) if isinstance(a, str) else a for a in record.args
                )
        return True


_configured = False


def setup_logging() -> None:
    """يُهيّئ التسجيل مرّة واحدة. المستوى عبر LOG_LEVEL (افتراضي INFO)."""
    global _configured
    if _configured:
        return
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    # نتجنّب تكرار الـ handlers عند إعادة التحميل (uvicorn --reload)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """ارجع logger مع ضمان التهيئة."""
    setup_logging()
    return logging.getLogger(name)
