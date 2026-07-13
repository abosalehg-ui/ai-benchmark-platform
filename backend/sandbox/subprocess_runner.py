"""Sandbox مبني على subprocess + قائمة سوداء.

أبسط backend ولا يحتاج تبعيات خارجية، لكنه أقل أماناً.
الـ blacklist سهلة التجاوز نظرياً، فيُنصح بـ Docker للنشر.

نضيف حدود موارد على أنظمة POSIX (ذاكرة، CPU، حجم ملفات، عدد عمليات)
عبر ``resource.setrlimit`` كطبقة دفاع ثانية بجانب مهلة الـ timeout.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from backend.sandbox.base import SandboxResult, is_code_safe

try:
    import resource  # POSIX فقط
except ImportError:  # Windows
    resource = None

# حدود الموارد (قابلة للضبط عبر env)
_MEM_BYTES = int(os.getenv("SANDBOX_SUBPROCESS_MEMORY_MB", "512")) * 1024 * 1024
_CPU_SECONDS = int(os.getenv("SANDBOX_SUBPROCESS_CPU_SECONDS", "15"))
_FSIZE_BYTES = int(os.getenv("SANDBOX_SUBPROCESS_FSIZE_MB", "10")) * 1024 * 1024


def _apply_rlimits() -> None:
    """يُطبَّق في العملية الابنة قبل exec لتقييد مواردها."""
    if resource is None:
        return
    for res, limit in (
        (resource.RLIMIT_AS, _MEM_BYTES),      # مساحة العنونة (ذاكرة)
        (resource.RLIMIT_CPU, _CPU_SECONDS),   # زمن المعالج
        (resource.RLIMIT_FSIZE, _FSIZE_BYTES), # أقصى حجم ملف يُكتب
    ):
        try:
            resource.setrlimit(res, (limit, limit))
        except (ValueError, OSError):
            pass


def run(
    code: str,
    test_code: str = "",
    timeout: int = 5,
    enforce_safety: bool = True,
) -> SandboxResult:
    full_code = f"{code}\n\n{test_code}"

    if enforce_safety:
        safe, reason = is_code_safe(full_code)
        if not safe:
            return SandboxResult(
                passed=False,
                blocked_reason=reason,
                error="الكود رُفض من فاحص الأمان",
                backend="subprocess",
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
                # حدود موارد + جلسة جديدة (يمنع الوصول لـ terminal الأب)
                preexec_fn=_apply_rlimits if resource is not None else None,
                start_new_session=resource is not None,
            )
            return SandboxResult(
                passed=result.returncode == 0,
                stdout=result.stdout[:2000],
                stderr=result.stderr[:2000],
                error=None if result.returncode == 0 else f"Exit code {result.returncode}",
                backend="subprocess",
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                passed=False,
                timed_out=True,
                error=f"انتهى الوقت المسموح ({timeout}s)",
                backend="subprocess",
            )
        except Exception as e:
            return SandboxResult(
                passed=False, error=f"{type(e).__name__}: {e}", backend="subprocess"
            )
