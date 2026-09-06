"""اختبارات الـ sandbox: التشغيل، الحظر، المهلة، حدود الموارد، واختيار backend."""
from __future__ import annotations

import os

import pytest

from backend.sandbox import (
    backend_status,
    current_backend_name,
    docker_runner,
    extract_python_code,
    run_python_code,
)


@pytest.fixture(autouse=True)
def pin_subprocess_backend(monkeypatch):
    """يثبّت backend الـ subprocess لكل اختبار في هذا الملف.

    أغلب ما هنا يختبر **دلالات مسار subprocess** تحديداً: القائمة السوداء،
    حدود ``resource``، والاستدعاء من خيوط. بلا تثبيت صريح كانت هذه
    الاختبارات ترث الافتراضي المحيط (``auto``)، فتنتقل إلى Docker على أي
    جهاز فيه daemon — وتقيس شيئاً آخر تماماً. الاختبارات التي تعني
    الافتراضي أو Docker تتجاوز هذا التثبيت بـ``monkeypatch`` في جسمها.
    """
    monkeypatch.setenv("SANDBOX_BACKEND", "subprocess")
    # نتيجة ``is_available`` صارت محفوظة لدقيقة (لتفادي تشغيل ``docker version``
    # لكل مسألة)؛ نُبطلها هنا حتى لا يرث اختبارٌ نتيجةَ اختبار قبله
    docker_runner.reset_availability_cache()


def test_runs_simple_code():
    result = run_python_code("def add(a, b): return a + b", "assert add(2, 3) == 5", timeout=5)
    assert result.passed, f"{result.error} / {result.stderr}"
    assert result.backend in {"subprocess", "docker"}


def test_blocks_dangerous_code():
    result = run_python_code("import os\nos.system('echo hi')", "", timeout=5)
    assert not result.passed
    assert result.blocked_reason is not None


def test_timeout_stops_infinite_loop():
    result = run_python_code("while True: pass", "", timeout=2, enforce_safety=False)
    assert not result.passed
    assert result.timed_out


@pytest.mark.skipif(os.name == "nt", reason="حدود الموارد POSIX فقط")
def test_memory_limit_is_enforced():
    """الحدود تُطبَّق بعد exec عبر مُشغِّل، لا عبر preexec_fn غير الآمن مع الخيوط."""
    result = run_python_code(
        "x = bytearray(2 * 1024 * 1024 * 1024)",  # 2 غيغابايت > الحدّ الافتراضي 512 ميغا
        "", timeout=20, enforce_safety=False,
    )
    assert not result.passed
    assert "MemoryError" in result.stderr or result.error


def test_sandbox_is_callable_from_a_thread():
    """HumanEval يستدعيه عبر asyncio.to_thread — نتأكّد أنه لا يعلّق."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(run_python_code, f"assert {i} + 1 == {i + 1}", "", 10, False)
            for i in range(4)
        ]
        results = [f.result(timeout=60) for f in futures]
    assert all(r.passed for r in results)


def test_extract_python_code():
    text = "شرح\n```python\ndef f():\n    return 1\n```\nخاتمة"
    assert extract_python_code(text) == "def f():\n    return 1"
    assert extract_python_code("بلا كتلة كود") == "بلا كتلة كود"


def test_backend_status_shape():
    status = backend_status()
    assert status["backend"] in {"subprocess", "docker"}
    assert isinstance(status["docker_available"], bool)
    assert isinstance(status["is_isolated"], bool)
    assert status["backend"] == current_backend_name()


def test_backend_selection_via_env(monkeypatch):
    monkeypatch.setenv("SANDBOX_BACKEND", "subprocess")
    assert current_backend_name() == "subprocess"

    monkeypatch.setenv("SANDBOX_BACKEND", "docker")
    assert current_backend_name() == "docker"

    monkeypatch.setenv("SANDBOX_BACKEND", "auto")
    expected = "docker" if docker_runner.is_available() else "subprocess"
    assert current_backend_name() == expected


def test_docker_hardening_flags():
    """نفحص بناء الأمر بدل تشغيل Docker — يعمل حتى بلا daemon."""
    import inspect

    src = inspect.getsource(docker_runner.run)
    for flag in ("--network=none", "--read-only", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges", "--user=65534:65534"):
        assert flag in src, f"علم تحصين مفقود: {flag}"
    # /tmp يجب ألا يكون قابلاً للتنفيذ وإلا ضعفت فائدة --read-only
    assert "noexec" in src
    assert ",exec" not in src


def test_docker_e2e_when_available():
    if not docker_runner.is_available() or os.getenv("RUN_DOCKER_TESTS") != "1":
        pytest.skip("Docker غير متاح أو RUN_DOCKER_TESTS!=1")

    r = docker_runner.run("print('hello from sandbox')", "", timeout=15)
    assert r.backend == "docker"
    assert r.passed, f"{r.error} / {r.stderr}"
    assert "hello" in r.stdout


# ============ الافتراضي الآمن + وصول علَم الأمان ============

def test_default_backend_prefers_isolation(monkeypatch):
    """الافتراضي صار auto: من لديه Docker يحصل على عزل حقيقي بلا ضبط شيء.

    القائمة السوداء لا يمكن أن تنجح مبدئياً (انظر الاختبار التالي)، فالافتراضي
    السابق ``subprocess`` كان يعني تنفيذ كود النماذج على الجهاز بلا عزل.
    """
    monkeypatch.delenv("SANDBOX_BACKEND", raising=False)
    expected = "docker" if docker_runner.is_available() else "subprocess"
    assert current_backend_name() == expected


def test_status_note_is_honest_about_blacklist_limits(monkeypatch):
    monkeypatch.setenv("SANDBOX_BACKEND", "subprocess")
    note = backend_status()["note"]
    assert "بلا عزل حقيقي" in note
    assert "قراءة الملفات" in note


@pytest.mark.parametrize("payload", [
    "print(open('/etc/hostname').read())",           # القائمة السوداء لا تحظر open
    "import importlib\nm = importlib.import_module('so' + 'cket')",
    "import ftplib",                                  # وحدة شبكة غير مذكورة
    "from pathlib import Path\nPath('x').write_text('y')",
])
def test_blacklist_is_known_to_be_bypassable(payload):
    """توثيق تنفيذي لحدود الفاحص: هذه الأنماط **تمرّ**.

    الاختبار يثبّت الواقع حتى لا يظنّ أحد أن القائمة السوداء حماية. الحماية
    الحقيقية هي backend الـ docker — ولهذا صار الافتراضي ``auto``.
    """
    from backend.sandbox import is_code_safe

    safe, _ = is_code_safe(payload)
    assert safe is True


def test_enforce_safety_flag_reaches_the_checker():
    """الخانة في الواجهة كانت بلا أثر: العلَم يصل الآن حتى is_code_safe."""
    blocked = run_python_code("import os\nos.system('echo hi')", "", timeout=5,
                              enforce_safety=True)
    assert blocked.blocked_reason is not None

    allowed = run_python_code("import os\nprint(os.system)", "", timeout=5,
                              enforce_safety=False)
    assert allowed.blocked_reason is None


# ============ docker_runner: بناء الأمر ومسارات الفشل ============

def test_docker_runner_builds_a_hardened_command(monkeypatch):
    """نفحص الأمر المبنيّ فعلياً بلا daemon — كان المسار الآمن أقلّ المسارات تغطيةً."""
    captured = {}

    class _Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(docker_runner.subprocess, "run", _fake_run)
    result = docker_runner.run("print(1)", "assert True", timeout=7)

    assert result.passed and result.backend == "docker"
    cmd = captured["cmd"]
    assert cmd[:2] == ["docker", "run"]
    for flag in ("--rm", "--network=none", "--read-only", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges", "--user=65534:65534"):
        assert flag in cmd
    assert cmd[-2:] == ["python", "solution.py"]
    # مهلة الجدار أوسع من مهلة الكود للسماح بإقلاع الحاوية
    assert captured["kwargs"]["timeout"] == 12


def test_docker_runner_makes_the_mount_readable_by_nobody(monkeypatch):
    """تحصين ``--user=65534`` كان يكسر الـ sandbox بصمت.

    ``TemporaryDirectory`` يُنشئ المجلّد بصلاحية 0700 لمالكه، والحاوية تعمل
    بمستخدم nobody. بلا صلاحية العبور على المجلّد يفشل كل تشغيل بـ
    «can't open file '/sandbox/solution.py': Permission denied» — وهو ما ظهر
    فور جعل الافتراضي ``auto`` على أجهزة فيها Docker.
    """
    import stat

    seen = {}

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        # نلتقط الصلاحيات وقت التشغيل: المجلّد يُحذف بعد الخروج من الـ context
        mount = cmd[cmd.index("-v") + 1].split(":")[0]
        seen["dir_mode"] = stat.S_IMODE(os.stat(mount).st_mode)
        seen["file_mode"] = stat.S_IMODE(os.stat(os.path.join(mount, "solution.py")).st_mode)
        return _Completed()

    monkeypatch.setattr(docker_runner.subprocess, "run", _fake_run)
    docker_runner.run("print(1)", "", timeout=5)

    # العبور (x) والقراءة (r) للجميع: بدونهما لا يستطيع nobody الوصول للملف
    assert seen["dir_mode"] & 0o055 == 0o055, oct(seen["dir_mode"])
    assert seen["file_mode"] & 0o044 == 0o044, oct(seen["file_mode"])
    # ولا نمنح صلاحية الكتابة لغير المالك
    assert seen["dir_mode"] & 0o022 == 0
    assert seen["file_mode"] & 0o022 == 0


def test_docker_runner_kills_container_on_timeout(monkeypatch):
    import subprocess as sp

    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            raise sp.TimeoutExpired(cmd, kwargs.get("timeout", 0))

        class _Ok:
            returncode = 0
            stdout = ""
            stderr = ""
        return _Ok()

    monkeypatch.setattr(docker_runner.subprocess, "run", _fake_run)
    result = docker_runner.run("while True: pass", "", timeout=3)

    assert result.timed_out and not result.passed
    # الحاوية تُقتل صراحةً بدل تركها تعمل بعد انتهاء المهلة
    assert any(c[:2] == ["docker", "kill"] for c in calls)


def test_docker_runner_reports_missing_docker(monkeypatch):
    def _fake_run(cmd, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(docker_runner.subprocess, "run", _fake_run)
    result = docker_runner.run("print(1)", "", timeout=5)
    assert not result.passed
    assert "Docker غير مثبّت" in result.error


# ============ فحص توفّر Docker: عملية واحدة لا واحدة لكل مسألة ============

def test_docker_availability_is_probed_once_per_minute(monkeypatch):
    """كان ``docker version`` يُشغَّل لكل مسألة HumanEval — 50 عملية لتشغيل 10×5."""
    docker_runner.reset_availability_cache()
    probes = []

    def _fake_probe():
        probes.append(1)
        return True

    monkeypatch.setattr(docker_runner, "_probe_docker", _fake_probe)
    for _ in range(10):
        assert docker_runner.is_available() is True
    assert len(probes) == 1, f"شُغّل الفحص {len(probes)} مرّة بدل مرّة واحدة"


def test_backend_status_asks_about_docker_once(monkeypatch):
    """نفس السؤال كان يُسأل مرّتين في الاستجابة الواحدة."""
    docker_runner.reset_availability_cache()
    calls = []
    monkeypatch.setattr(docker_runner, "_probe_docker", lambda: calls.append(1) or False)
    monkeypatch.delenv("SANDBOX_BACKEND", raising=False)
    status = backend_status()
    assert status["docker_available"] is False
    assert len(calls) == 1


def test_availability_cache_can_be_invalidated(monkeypatch):
    """تثبيت Docker أثناء التشغيل يجب أن يُرى بعد إبطال الـ cache."""
    docker_runner.reset_availability_cache()
    state = {"available": False}
    monkeypatch.setattr(docker_runner, "_probe_docker", lambda: state["available"])
    assert docker_runner.is_available() is False
    state["available"] = True
    assert docker_runner.is_available() is False  # ما زال من الـ cache
    docker_runner.reset_availability_cache()
    assert docker_runner.is_available() is True
