"""اختبارات طبقة قاعدة البيانات: دورة الحياة، الـ cache، H2H، وإحصاء الدقة."""
from __future__ import annotations

from backend.db import wilson_interval


def test_wilson_interval():
    ci = wilson_interval(7, 10)
    assert 0.0 <= ci["lower"] < 0.7 < ci["upper"] <= 1.0
    assert ci["margin"] > 0

    assert wilson_interval(0, 0) == {"center": 0.0, "margin": 0.0, "lower": 0.0, "upper": 0.0}

    perfect = wilson_interval(10, 10)
    assert perfect["upper"] == 1.0 and perfect["lower"] < 1.0

    worst = wilson_interval(0, 10)
    assert worst["lower"] == 0.0 and worst["upper"] > 0.0

    assert wilson_interval(500, 1000)["margin"] < wilson_interval(50, 100)["margin"]


def test_run_lifecycle(temp_db):
    run_id = temp_db.create_run("humaneval", 5, {"test": True})
    assert run_id

    temp_db.insert_result(
        run_id, "anthropic", "claude-opus-5", "p1",
        correct=True, raw_score=1.0, latency_ms=100.0,
        input_tokens=50, output_tokens=30, cost_usd=0.001,
        response_text="def f(): pass", judgment="passed",
    )
    temp_db.finish_run(run_id, "completed")

    run = temp_db.get_run(run_id)
    assert run["status"] == "completed"
    assert len(run["models"]) == 1
    assert run["models"][0]["n"] == 1


def test_insert_result_tolerates_none_text(temp_db):
    """تمرير None صراحةً كان يرفع TypeError ويُسقط الـ run كاملاً."""
    run_id = temp_db.create_run("mmlu", 1, {})
    temp_db.insert_result(
        run_id, "openai", "gpt-5-mini", "p1",
        correct=False, raw_score=0.0, latency_ms=1.0,
        input_tokens=1, output_tokens=1, cost_usd=0.0,
        response_text=None, judgment=None, error="boom",
    )
    page = temp_db.get_run_details(run_id)
    assert page["details"][0]["response_text"] == ""


def test_accuracy_and_raw_score_are_separate_metrics(temp_db):
    """كانت accuracy تُحسب من raw_score المستمر بينما CI من correct الثنائية."""
    run_id = temp_db.create_run("tool_use", 2, {})
    # الأداة صحيحة والمعاملات خاطئة => correct=False لكن raw_score=0.5
    temp_db.insert_result(run_id, "openai", "gpt-5-mini", "p1",
                          correct=False, raw_score=0.5, latency_ms=1, input_tokens=1,
                          output_tokens=1, cost_usd=0, response_text="", judgment="")
    temp_db.insert_result(run_id, "openai", "gpt-5-mini", "p2",
                          correct=True, raw_score=1.0, latency_ms=1, input_tokens=1,
                          output_tokens=1, cost_usd=0, response_text="", judgment="")
    temp_db.finish_run(run_id)

    m = temp_db.get_run(run_id)["models"][0]
    assert m["accuracy"] == 0.5       # 1 من 2 صحيحة — نفس كمية فاصل الثقة
    assert m["avg_raw_score"] == 0.75  # المتوسط المرجّح مقياس منفصل
    assert m["n_correct"] == 1


def test_response_cache_roundtrip(temp_db):
    key = temp_db.make_cache_key("anthropic", "claude-haiku-4-5", "ما 1+1؟", "system", 0.0)
    assert temp_db.cache_get(key) is None

    temp_db.cache_put(key, "anthropic", "claude-haiku-4-5",
                      text="2", input_tokens=10, output_tokens=1,
                      cost_usd=0.0001, latency_ms=42.5)

    got = temp_db.cache_get(key)
    assert got["response_text"] == "2" and got["input_tokens"] == 10

    same = temp_db.make_cache_key("anthropic", "claude-haiku-4-5", "ما 1+1؟", "system", 0.0)
    other = temp_db.make_cache_key("anthropic", "claude-haiku-4-5", "ما 2+2؟", "system", 0.0)
    assert same == key and other != key
    assert temp_db.cache_stats()["entries"] == 1
    assert temp_db.cache_clear() == 1


def test_head_to_head_matrix(temp_db):
    run_id = temp_db.create_run("saudi_legal", 3, {})
    for pid, a_ok, b_ok in [("p1", True, True), ("p2", True, False), ("p3", False, False)]:
        for provider, model, ok in (("anthropic", "claude-x", a_ok), ("openai", "gpt-x", b_ok)):
            temp_db.insert_result(run_id, provider, model, pid,
                                  correct=ok, raw_score=1.0 if ok else 0.0,
                                  latency_ms=10, input_tokens=1, output_tokens=1,
                                  cost_usd=0, response_text="", judgment="", error=None)
    temp_db.finish_run(run_id)

    h2h = temp_db.head_to_head(run_id)
    idx = {(m["provider"], m["model"]): i for i, m in enumerate(h2h["models"])}
    cell = h2h["matrix"][idx[("anthropic", "claude-x")]][idx[("openai", "gpt-x")]]
    assert cell == {
        "both_correct": 1, "a_only": 1, "b_only": 0,
        "both_wrong": 1, "n_compared": 3, "a_wins_pct": 33.3,
    }
    diag = h2h["matrix"][idx[("anthropic", "claude-x")]][idx[("anthropic", "claude-x")]]
    assert diag["a_only"] == 0 and diag["b_only"] == 0


def test_head_to_head_returns_none_for_missing_run(temp_db):
    assert temp_db.head_to_head("nonexistent") is None


def test_delete_run_removes_results(temp_db):
    run_id = temp_db.create_run("mmlu", 1, {})
    temp_db.insert_result(run_id, "openai", "gpt-5-mini", "p1",
                          correct=True, raw_score=1.0, latency_ms=1, input_tokens=1,
                          output_tokens=1, cost_usd=0, response_text="", judgment="")
    assert temp_db.delete_run(run_id) is True
    assert temp_db.get_run(run_id) is None
    assert temp_db.delete_run(run_id) is False
