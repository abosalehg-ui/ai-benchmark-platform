"""Sandbox مبني على subprocess + قائمة سوداء.

أبسط backend ولا يحتاج تبعيات خارجية، لكنه أقل أماناً.
الـ blacklist سهلة التجاوز نظرياً، فيُنصح بـ Docker للنشر.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from backend.sandbox.base import SandboxResult, is_code_safe


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
