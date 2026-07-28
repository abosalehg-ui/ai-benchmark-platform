"""Sandbox مبني على subprocess + قائمة سوداء.

أبسط backend ولا يحتاج تبعيات خارجية، لكنه أقل أماناً.
الـ blacklist سهلة التجاوز نظرياً، فيُنصح بـ Docker للنشر.

حدود الموارد (ذاكرة، CPU، حجم ملفات) تُطبَّق على أنظمة POSIX عبر
``resource.setrlimit`` كطبقة دفاع ثانية بجانب مهلة الـ timeout — لكن
**بعد** exec وليس عبر ``preexec_fn``: توثيق CPython صريح أنّ
``preexec_fn`` غير آمن في وجود خيوط، و``HumanEvalBenchmark`` يستدعي
الـ sandbox من داخل ``asyncio.to_thread`` (أي من خيط)، فقد يحدث deadlock
بعد fork لو كان خيط آخر يمسك قفلاً في تلك اللحظة.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from backend.logging_config import get_logger
from backend.sandbox.base import SandboxResult, is_code_safe

logger = get_logger(__name__)

try:
    import resource  # noqa: F401  — POSIX فقط؛ نفحص توفّره فقط
    _HAS_RESOURCE = True
except ImportError:  # Windows
    _HAS_RESOURCE = False

# حدود الموارد (قابلة للضبط عبر env)
_MEM_MB = int(os.getenv("SANDBOX_SUBPROCESS_MEMORY_MB", "512"))
_CPU_SECONDS = int(os.getenv("SANDBOX_SUBPROCESS_CPU_SECONDS", "15"))
_FSIZE_MB = int(os.getenv("SANDBOX_SUBPROCESS_FSIZE_MB", "10"))

# مُشغِّل صغير يضبط الحدود على نفسه ثم ينفّذ ملف الحل.
# يعمل بعد exec في عملية أحادية الخيط، فلا مشكلة fork/threads.
_LAUNCHER = """\
import resource, runpy, sys
mem, cpu, fsize = {mem}, {cpu}, {fsize}
for res, limit in (
    (resource.RLIMIT_AS, mem * 1024 * 1024),
    (resource.RLIMIT_CPU, cpu),
    (resource.RLIMIT_FSIZE, fsize * 1024 * 1024),
):
    try:
        resource.setrlimit(res, (limit, limit))
    except (ValueError, OSError):
        pass
runpy.run_path(sys.argv[1], run_name="__main__")
"""


def _build_command(script_path: str) -> list[str]:
    """أمر التشغيل: مع حدود الموارد على POSIX، ومباشر على Windows."""
    if not _HAS_RESOURCE:
        return [sys.executable, script_path]
    launcher = _LAUNCHER.format(mem=_MEM_MB, cpu=_CPU_SECONDS, fsize=_FSIZE_MB)
    return [sys.executable, "-c", launcher, script_path]


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
            logger.info("sandbox: كود مرفوض من فاحص الأمان — %s", reason)
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
                _build_command(script_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
                # جلسة جديدة: يمنع الوصول لـ terminal الأب ويجعل الإشارات
                # تصل للمجموعة كاملة بدل العملية الأولى فقط
                start_new_session=_HAS_RESOURCE,
            )
            return SandboxResult(
                passed=result.returncode == 0,
                stdout=result.stdout[:2000],
                stderr=result.stderr[:2000],
                error=None if result.returncode == 0 else f"Exit code {result.returncode}",
                backend="subprocess",
            )
        except subprocess.TimeoutExpired:
            logger.info("sandbox: انتهت المهلة (%ss)", timeout)
            return SandboxResult(
                passed=False,
                timed_out=True,
                error=f"انتهى الوقت المسموح ({timeout}s)",
                backend="subprocess",
            )
        except Exception as e:
            logger.exception("sandbox: فشل غير متوقّع في subprocess runner")
            return SandboxResult(
                passed=False, error=f"{type(e).__name__}: {e}", backend="subprocess"
            )
