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
