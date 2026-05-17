"""أنواع وأدوات مشتركة بين كل sandbox backends."""
from __future__ import annotations

import re
from dataclasses import dataclass


# قائمة سوداء للاستيرادات الخطرة (تُستخدم في subprocess backend فقط؛
# Docker backend معزول فلا يحتاجها)
DANGEROUS_IMPORTS = [
    r"\bos\.system\b",
    r"\bos\.popen\b",
    r"\bos\.exec",
    r"\bos\.fork\b",
    r"\bos\.remove\b",
    r"\bos\.rmdir\b",
    r"\bos\.unlink\b",
    r"\bshutil\.rmtree\b",
    r"\bsubprocess\b",
    r"\b__import__\b",
    r"\beval\b",
    r"\bexec\b",
    r"\bcompile\b",
    r"\bsocket\b",
    r"\burllib\b",
    r"\brequests\b",
    r"\bhttpx\b",
]


@dataclass
class SandboxResult:
    """نتيجة تشغيل الكود."""
    passed: bool
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    timed_out: bool = False
    blocked_reason: str | None = None
    backend: str = ""  # "subprocess" أو "docker"


def is_code_safe(code: str) -> tuple[bool, str | None]:
    """فحص أولي: هل الكود يحتوي على عمليات خطرة؟"""
    for pattern in DANGEROUS_IMPORTS:
        if re.search(pattern, code):
            return False, f"الكود يحتوي على عملية خطرة: {pattern}"
    return True, None


def extract_python_code(text: str) -> str:
    """استخراج كود بايثون من رد النموذج (يبحث عن code blocks)."""
    pattern = r"```(?:python|py)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return max(matches, key=len).strip()
    return text.strip()
