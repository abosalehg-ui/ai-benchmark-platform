"""Sandbox مبني على Docker — عزل قوي وآمن.

كل تشغيل في container مؤقت:
- بدون شبكة (--network=none)
- محدود الذاكرة والـ CPU
- نظام ملفات للقراءة فقط (--read-only)
- مستخدم غير root
- pids limit
- يُحذَف تلقائياً بعد الانتهاء (--rm)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid

from backend.sandbox.base import SandboxResult

DEFAULT_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "python:3.11-slim")
DEFAULT_MEMORY = os.getenv("SANDBOX_DOCKER_MEMORY", "256m")
DEFAULT_CPUS = os.getenv("SANDBOX_DOCKER_CPUS", "0.5")
DEFAULT_PIDS = os.getenv("SANDBOX_DOCKER_PIDS", "64")


def is_available() -> bool:
    """هل Docker متاح وقابل للاستخدام؟"""
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def run(
    code: str,
    test_code: str = "",
    timeout: int = 5,
    enforce_safety: bool = True,  # noqa: ARG001 -- Docker معزول، فحص الكود غير ضروري
) -> SandboxResult:
    full_code = f"{code}\n\n{test_code}"

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "solution.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_code)
        os.chmod(script_path, 0o644)

        name = f"benchsbx-{uuid.uuid4().hex[:10]}"
        cmd = [
            "docker", "run",
            "--name", name,
            "--rm",
            "--network=none",
            f"--memory={DEFAULT_MEMORY}",
            f"--cpus={DEFAULT_CPUS}",
            f"--pids-limit={DEFAULT_PIDS}",
            "--read-only",
            # noexec: يُبطل تنفيذ ملفات يكتبها الكود في /tmp، وهو ما كان
            # يُضعف فائدة --read-only. الكود نفسه يُنفَّذ من /sandbox المركّب ro
            "--tmpfs=/tmp:size=64m,noexec,nosuid,nodev",
            "--security-opt=no-new-privileges",
            "--cap-drop=ALL",  # الحاوية لا تحتاج أي قدرة نواة
            "--user=65534:65534",  # nobody:nogroup
            "-v", f"{tmpdir}:/sandbox:ro",
            "-w", "/sandbox",
            DEFAULT_IMAGE,
            "python", "solution.py",
        ]

        # نمنح Docker مهلة إضافية (5s) فوق timeout الكود للسماح بـ startup
        wall_timeout = timeout + 5

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=wall_timeout,
            )
            return SandboxResult(
                passed=result.returncode == 0,
                stdout=result.stdout[:2000],
                stderr=result.stderr[:2000],
                error=(
                    None if result.returncode == 0
                    else f"Exit code {result.returncode}"
                ),
                backend="docker",
            )
        except subprocess.TimeoutExpired:
            # نقتل الـ container إذا لم يخرج
            subprocess.run(
                ["docker", "kill", name],
                capture_output=True, timeout=5,
            )
            return SandboxResult(
                passed=False,
                timed_out=True,
                error=f"انتهى الوقت المسموح ({timeout}s)",
                backend="docker",
            )
        except FileNotFoundError:
            return SandboxResult(
                passed=False,
                error="Docker غير مثبّت — استخدم SANDBOX_BACKEND=subprocess",
                backend="docker",
            )
        except Exception as e:
            return SandboxResult(
                passed=False,
                error=f"{type(e).__name__}: {e}",
                backend="docker",
            )
