"""واجهة موحّدة لكل sandbox backends.

اختيار الـ backend عبر SANDBOX_BACKEND env:
- "auto" (افتراضي): Docker إن وُجد، وإلا subprocess
- "docker": آمن، يحتاج Docker مثبّتاً
- "subprocess": سريع، يعتمد على blacklist — بلا عزل حقيقي

**لماذا الافتراضي "auto" لا "subprocess":** الكود المُنفَّذ هنا يأتي من نموذج
لغوي خارجي، والقائمة السوداء في ``base.py`` لا يمكن أن تنجح مبدئياً — بايثون
يمنح عشرات الطرق للوصول لأي شيء (``importlib``، ``getattr`` على البنى المدمجة،
وحدات شبكة غير مذكورة مثل ``ftplib``). وهي أصلاً لا تحظر ``open()`` فقراءة
``~/.ssh`` أو ``~/.aws/credentials`` تمرّ منها. ``auto`` يمنح العزل الحقيقي لمن
لديه Docker بلا أن يكسر شيئاً على من ليس لديه.

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
    pref = os.getenv("SANDBOX_BACKEND", "auto").lower()
    if pref == "docker":
        return "docker"
    if pref == "subprocess":
        return "subprocess"
    # "auto" وأي قيمة غير معروفة: نفضّل العزل الحقيقي متى توفّر
    return "docker" if docker_runner.is_available() else "subprocess"


def current_backend_name() -> str:
    """ارجع اسم backend الذي سيُستخدم في الاستدعاء التالي."""
    return _choose_backend()


#: نصّ صريح عن حدود مسار subprocess. الصيغة القديمة («مناسب للاستخدام المحلي
#: فقط») كانت تُقلّل من الخطر: «محلي» هو بالضبط المكان الذي فيه مفاتيح المستخدم
#: ومستودعاته، والقائمة السوداء لا تحمي منه.
UNISOLATED_NOTE = (
    "subprocess بلا عزل حقيقي: القائمة السوداء لا تمنع قراءة الملفات "
    "(‎~/.ssh‎، ‎~/.aws‎) ولا الشبكة الصادرة. كود النماذج سيُنفَّذ على جهازك."
)
ISOLATED_NOTE = "Docker معزول — بلا شبكة، نظام ملفات للقراءة فقط، ومستخدم غير جذر."


def backend_status() -> dict:
    """معلومات عن backend المستخدم — لعرضها في الواجهة.

    ``is_available`` كان يُستدعى مرّتين هنا (مرّة داخل ``_choose_backend``
    ومرّة للحقل) — نفس السؤال يُسأل مرّتين في نفس الاستجابة.
    """
    docker_available = docker_runner.is_available()
    chosen = _choose_backend()
    return {
        "backend": chosen,
        "docker_available": docker_available,
        "is_isolated": chosen == "docker",
        "note": ISOLATED_NOTE if chosen == "docker" else UNISOLATED_NOTE,
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
    "ISOLATED_NOTE",
    "UNISOLATED_NOTE",
    "SandboxResult",
    "backend_status",
    "current_backend_name",
    "extract_python_code",
    "is_code_safe",
    "run_python_code",
]
