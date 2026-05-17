"""واجهة موحّدة لكل sandbox backends.

اختيار الـ backend عبر SANDBOX_BACKEND env:
- "subprocess" (افتراضي): سريع، يعتمد على blacklist
- "docker": آمن، يحتاج Docker مثبّتاً
- "auto": Docker إن وُجد، وإلا subprocess

API عام:
- run_python_code(code, test_code, timeout, enforce_safety) -> SandboxResult
- extract_python_code(text) -> str
- current_backend_name() -> str
"""
from __future__ import annotations

import os

from backend.sandbox import docker_runner, subprocess_runner
from backend.sandbox.base import (
    DANGEROUS_IMPORTS,
    SandboxResult,
    extract_python_code,
    is_code_safe,
)


def _choose_backend() -> str:
    pref = os.getenv("SANDBOX_BACKEND", "subprocess").lower()
    if pref == "docker":
        return "docker"
    if pref == "auto":
        return "docker" if docker_runner.is_available() else "subprocess"
    return "subprocess"


def current_backend_name() -> str:
    """ارجع اسم backend الذي سيُستخدم في الاستدعاء التالي."""
    return _choose_backend()


def backend_status() -> dict:
    """معلومات عن backend المستخدم — لعرضها في الواجهة."""
    chosen = _choose_backend()
    return {
        "backend": chosen,
        "docker_available": docker_runner.is_available(),
        "is_isolated": chosen == "docker",
        "note": (
            "Docker معزول — آمن للنشر." if chosen == "docker"
            else "subprocess يعتمد على blacklist — مناسب للاستخدام المحلي فقط."
        ),
    }


def run_python_code(
    code: str,
    test_code: str = "",
    timeout: int = 5,
    enforce_safety: bool = True,
) -> SandboxResult:
    """تشغيل كود بايثون داخل الـ sandbox المختار."""
    backend = _choose_backend()
    if backend == "docker":
        return docker_runner.run(code, test_code, timeout, enforce_safety)
    return subprocess_runner.run(code, test_code, timeout, enforce_safety)


__all__ = [
    "DANGEROUS_IMPORTS",
    "SandboxResult",
    "backend_status",
    "current_backend_name",
    "extract_python_code",
    "is_code_safe",
    "run_python_code",
]
