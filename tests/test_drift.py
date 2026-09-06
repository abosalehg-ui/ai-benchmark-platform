"""اختبارات تتبّع الانحراف عبر الزمن.

التركيز على المزلق الأساسي: ألّا تُسمّى فروق العيّنة «انحرافاً».
"""
from __future__ import annotations

import json

from backend.drift import drift_series


def _seed_run(db, *, benchmark, provider, model, n, n_correct,
              created_at, status="completed", categories=None, difficulties=None,
              cost=0.001, latency=100.0):
    """يزرع تشغيلاً بنتائج محدّدة الدقّة، مع ضبط created_at يدوياً."""
    config = {
        "benchmark": benchmark,
        "categories": categories or [],
        "difficulties": difficulties or [],
    }
    run_id = db.create_run(benchmark, n, config)
    for i in range(n):
        db.insert_result(
            run_id, provider, model, f"p{i}",
            correct=i < n_correct, raw_score=1.0 if i < n_correct else 0.0,
            latency_ms=latency, input_tokens=1, output_tokens=1,
            cost_usd=cost, response_text="", judgment="",
        )
    db.finish_run(run_id, status)
    with db.get_conn() as conn:
        conn.execute("UPDATE runs SET created_at = ? WHERE id = ?", (created_at, run_id))
    return run_id


DAY = 86400.0


# ============ السلسلة الأساسية ============

def test_series_is_ordered_and_carries_wilson_interval(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=20, n_correct=16, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=20, n_correct=12, created_at=1000.0 + 30 * DAY)

    data = drift_series("mmlu")
    assert data["n_models"] == 1
    points = data["series"][0]["points"]
    assert [p["created_at"] for p in points] == sorted(p["created_at"] for p in points)
    assert points[0]["accuracy"] == 0.8
    assert points[1]["accuracy"] == 0.6
    # فاصل ويلسون محسوب لكل نقطة، لا للأخيرة فقط
    assert all(0.0 <= p["ci_lower"] <= p["accuracy"] <= p["ci_upper"] <= 1.0 for p in points)


def test_separate_series_per_model(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="a",
              n=10, n_correct=8, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="anthropic", model="b",
              n=10, n_correct=5, created_at=1000.0)

    data = drift_series("mmlu")
    assert data["n_models"] == 2
    keys = {(s["provider"], s["model"]) for s in data["series"]}
    assert keys == {("openai", "a"), ("anthropic", "b")}


def test_other_benchmarks_are_not_mixed_in(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=7, created_at=1000.0)
    _seed_run(temp_db, benchmark="gsm8k", provider="openai", model="m",
              n=10, n_correct=2, created_at=2000.0)

    assert drift_series("mmlu")["series"][0]["n_runs"] == 1
    assert drift_series("gsm8k")["series"][0]["points"][0]["accuracy"] == 0.2


def test_empty_benchmark_returns_empty_series(temp_db):
    data = drift_series("mmlu")
    assert data == {"benchmark": "mmlu", "series": [], "n_models": 0, "trackable": []}


# ============ استبعاد التشغيلات الناقصة ============

def test_partial_runs_are_excluded_by_default(temp_db):
    """تشغيل توقّف على الميزانية عيّنته ناقصة — إدراجه يُظهر هبوطاً وهمياً."""
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=20, n_correct=16, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=3, n_correct=0, created_at=2000.0, status="aborted_budget")

    assert drift_series("mmlu")["series"][0]["n_runs"] == 1
    assert drift_series("mmlu", include_partial=True)["series"][0]["n_runs"] == 2


# ============ النطاق: جوهر الميزة ============

def test_change_is_computed_only_between_comparable_scopes(temp_db):
    """تشغيل 10 مسائل بعد تشغيل 100 ليس انحرافاً — الفرق من العيّنة."""
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=20, n_correct=16, created_at=1000.0)          # 80% على 20
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=20, n_correct=10, created_at=2000.0)          # 50% على 20
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=4, n_correct=4, created_at=3000.0)            # 100% على 4 — نطاق مختلف

    s = drift_series("mmlu")["series"][0]
    assert s["mixed_scopes"] is True
    # آخر نقطة نطاقها فريد ⇒ لا نظير لها ⇒ لا تُقارَن
    assert s["latest_change"] is None


def test_change_skips_back_to_the_last_comparable_point(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=20, n_correct=16, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=5, n_correct=5, created_at=2000.0)            # نطاق دخيل بينهما
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=20, n_correct=10, created_at=3000.0)

    change = drift_series("mmlu")["series"][0]["latest_change"]
    assert change is not None
    assert change["from_accuracy"] == 0.8
    assert change["to_accuracy"] == 0.5
    assert change["delta_pct_points"] == -30.0


def test_filters_make_scopes_incomparable(temp_db):
    """نفس عدد المسائل لكن بفلتر تصنيف مختلف = عيّنة مختلفة."""
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=9, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=3, created_at=2000.0, categories=["تاريخ"])

    s = drift_series("mmlu")["series"][0]
    assert s["mixed_scopes"] is True
    assert s["latest_change"] is None


def test_scope_label_is_human_readable(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=5, created_at=1000.0, categories=["طب"],
              difficulties=["صعب"])
    label = drift_series("mmlu")["series"][0]["points"][0]["scope_label"]
    assert "10 مسألة" in label and "طب" in label and "صعب" in label

    _seed_run(temp_db, benchmark="gsm8k", provider="openai", model="m",
              n=7, n_correct=1, created_at=1000.0)
    plain = drift_series("gsm8k")["series"][0]["points"][0]["scope_label"]
    assert "كل التصنيفات" in plain


# ============ الدلالة الإحصائية ============

def test_small_sample_swing_is_not_flagged_significant(temp_db):
    """3/5 ← 2/5 تقلّب عيّنة صغيرة، لا انحراف. إنذار كاذب هنا يكلّف المستخدم."""
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=5, n_correct=3, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=5, n_correct=2, created_at=2000.0)

    change = drift_series("mmlu")["series"][0]["latest_change"]
    assert change["delta_pct_points"] == -20.0
    assert change["significant"] is False


def test_large_consistent_drop_is_flagged_significant(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=200, n_correct=190, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=200, n_correct=100, created_at=2000.0)

    change = drift_series("mmlu")["series"][0]["latest_change"]
    assert change["significant"] is True
    assert change["delta_pct_points"] == -45.0


def test_identical_results_report_no_change(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=50, n_correct=40, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=50, n_correct=40, created_at=2000.0)

    change = drift_series("mmlu")["series"][0]["latest_change"]
    assert change["delta_pct_points"] == 0.0
    assert change["significant"] is False


def test_days_apart_is_reported(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=8, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=6, created_at=1000.0 + 14 * DAY)

    assert drift_series("mmlu")["series"][0]["latest_change"]["days_apart"] == 14.0


def test_single_run_has_no_change_and_is_not_trackable(temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=8, created_at=1000.0)

    data = drift_series("mmlu")
    assert data["series"][0]["latest_change"] is None
    assert data["trackable"] == []


def test_max_runs_keeps_the_most_recent(temp_db):
    for i in range(6):
        _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
                  n=10, n_correct=i, created_at=1000.0 + i * DAY)

    points = drift_series("mmlu", max_runs=3)["series"][0]["points"]
    assert len(points) == 3
    assert [p["n_correct"] for p in points] == [3, 4, 5]


def test_cost_and_latency_travel_with_each_point(temp_db):
    """الانحراف ليس في الدقّة وحدها: مزوّد قد يبطئ أو يغلي بلا تغيّر الدقّة."""
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=8, created_at=1000.0, cost=0.01, latency=200.0)

    point = drift_series("mmlu")["series"][0]["points"][0]
    assert point["total_cost"] == 0.1
    assert point["avg_latency_ms"] == 200.0


# ============ طبقة HTTP ============

def test_drift_endpoint_returns_series(client, temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=8, created_at=1000.0)
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=10, n_correct=4, created_at=2000.0)

    body = client.get("/api/drift", params={"benchmark": "mmlu"}).json()
    assert body["n_models"] == 1
    assert len(body["trackable"]) == 1
    assert body["series"][0]["latest_change"]["delta_pct_points"] == -40.0


def test_drift_endpoint_rejects_unknown_benchmark(client):
    assert client.get("/api/drift", params={"benchmark": "nope"}).status_code == 404


def test_drift_endpoint_validates_max_runs(client):
    for bad in (1, 500):
        r = client.get("/api/drift", params={"benchmark": "mmlu", "max_runs": bad})
        assert r.status_code == 422


def test_drift_endpoint_is_protected_by_token(temp_db, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    from fastapi.testclient import TestClient

    import backend.main as main

    with TestClient(main.app) as c:
        assert c.get("/api/drift", params={"benchmark": "mmlu"}).status_code == 401


def test_drift_serialises_arabic_scope_labels(client, temp_db):
    _seed_run(temp_db, benchmark="saudi_legal", provider="openai", model="m",
              n=4, n_correct=2, created_at=1000.0, categories=["نظام العمل"])
    body = client.get("/api/drift", params={"benchmark": "saudi_legal"}).json()
    assert "نظام العمل" in body["series"][0]["points"][0]["scope_label"]


def test_config_json_corruption_does_not_crash_the_endpoint(client, temp_db):
    """صفّ قديم أو تالف في config_json يجب ألا يُسقط الصفحة كاملة."""
    run_id = _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
                       n=5, n_correct=3, created_at=1000.0)
    with temp_db.get_conn() as conn:
        conn.execute("UPDATE runs SET config_json = ? WHERE id = ?", ("{ليس JSON", run_id))

    body = client.get("/api/drift", params={"benchmark": "mmlu"}).json()
    assert body["n_models"] == 1
    assert "5 مسألة" in body["series"][0]["points"][0]["scope_label"]


def test_scope_key_is_stable_across_equivalent_configs(temp_db):
    """ترتيب التصنيفات في الطلب لا يجب أن يجعل تشغيلين غير قابلين للمقارنة."""
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=6, n_correct=4, created_at=1000.0, categories=["طب", "تاريخ"])
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=6, n_correct=2, created_at=2000.0, categories=["تاريخ", "طب"])

    s = drift_series("mmlu")["series"][0]
    assert s["mixed_scopes"] is False
    assert s["latest_change"] is not None


def test_json_encoding_keeps_arabic_readable(client, temp_db):
    _seed_run(temp_db, benchmark="mmlu", provider="openai", model="m",
              n=3, n_correct=1, created_at=1000.0)
    raw = client.get("/api/drift", params={"benchmark": "mmlu"}).text
    assert "مسألة" in raw
    assert json.loads(raw)["n_models"] == 1


def test_runs_with_a_failed_model_still_track_the_healthy_ones(temp_db):
    """``completed_with_errors`` تشغيل مكتمل العيّنة للنماذج التي نجحت.

    استبعاده كلّياً كان يعني أن تعثّر نموذج واحد يُخرج الأربعة الأخرى من
    التتبّع — عقوبة جماعية على بيانات سليمة.
    """
    _seed_run(temp_db, benchmark="saudi_legal", provider="openai", model="gpt-5.4",
              n=10, n_correct=8, created_at=1000.0, status="completed")
    _seed_run(temp_db, benchmark="saudi_legal", provider="openai", model="gpt-5.4",
              n=10, n_correct=3, created_at=2000.0, status="completed_with_errors")

    data = drift_series("saudi_legal")
    series = [s for s in data["series"] if s["model"] == "gpt-5.4"][0]
    assert series["n_runs"] == 2
    assert series["latest_change"] is not None


def test_genuinely_aborted_runs_remain_excluded(temp_db):
    """الميزانية والانقطاع يتركان عيّنة ناقصة فعلاً — تلك تبقى مستبعَدة."""
    _seed_run(temp_db, benchmark="saudi_legal", provider="openai", model="gpt-5.4",
              n=10, n_correct=8, created_at=1000.0, status="completed")
    _seed_run(temp_db, benchmark="saudi_legal", provider="openai", model="gpt-5.4",
              n=3, n_correct=0, created_at=2000.0, status="aborted_budget")

    series = [s for s in drift_series("saudi_legal")["series"] if s["model"] == "gpt-5.4"][0]
    assert series["n_runs"] == 1
