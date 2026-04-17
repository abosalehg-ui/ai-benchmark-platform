"""صندوق رمل (Sandbox) لتشغيل الكود المولّد من النماذج بأمان."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass


# قائمة سوداء للاستيرادات الخطرة
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


def is_code_safe(code: str) -> tuple[bool, str | None]:
    """فحص أولي: هل الكود يحتوي على عمليات خطرة؟"""
    for pattern in DANGEROUS_IMPORTS:
        if re.search(pattern, code):
            return False, f"الكود يحتوي على عملية خطرة: {pattern}"
    return True, None


def run_python_code(
    code: str,
    test_code: str = "",
    timeout: int = 5,
    enforce_safety: bool = True,
) -> SandboxResult:
    """تشغيل كود بايثون مع اختبارات. آمن بشكل بسيط (subprocess + timeout).

    Args:
        code: الكود المولّد (الحل)
        test_code: كود الاختبارات (assertions أو دوال test)
        timeout: مدة الانتظار القصوى بالثواني
        enforce_safety: هل نطبّق فحص الأمان (افتراضياً نعم)

    Returns:
        SandboxResult يحتوي على النتيجة + stdout/stderr.
    """
    full_code = f"{code}\n\n{test_code}"

    if enforce_safety:
        safe, reason = is_code_safe(full_code)
        if not safe:
            return SandboxResult(
                passed=False,
                blocked_reason=reason,
                error="الكود رُفض من فاحص الأمان",
            )

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "solution.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_code)

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
            )
            return SandboxResult(
                passed=result.returncode == 0,
                stdout=result.stdout[:2000],
                stderr=result.stderr[:2000],
                error=None if result.returncode == 0 else f"Exit code {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                passed=False,
                timed_out=True,
                error=f"انتهى الوقت المسموح ({timeout}s)",
            )
        except Exception as e:
            return SandboxResult(passed=False, error=f"{type(e).__name__}: {e}")


def extract_python_code(text: str) -> str:
    """استخراج كود بايثون من رد النموذج (يبحث عن code blocks)."""
    # نبحث عن ```python ... ``` أولاً
    pattern = r"```(?:python|py)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        # نأخذ أطول كتلة (عادةً الحل الفعلي)
        return max(matches, key=len).strip()
    return text.strip()
