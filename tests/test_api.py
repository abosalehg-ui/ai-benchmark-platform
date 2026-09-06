"""اختبارات طبقة HTTP — كانت الطبقة الوحيدة بلا أي تغطية.

تغطّي: التحقّق من المدخلات، رموز الحالة، الرؤوس الأمنية، المصادقة
الاختيارية، حماية SSRF، وحقن الصيغ في CSV.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ============ المسارات الأساسية ============

def test_benchmarks_endpoint(client):
    r = client.get("/api/benchmarks")
    assert r.status_code == 200
    ids = {b["id"] for b in r.json()["benchmarks"]}
    assert "saudi_legal" in ids
    assert all("problems_count" in b for b in r.json()["benchmarks"])


def test_providers_endpoint(client):
    r = client.get("/api/providers")
    assert r.status_code == 200
    providers = {p["id"]: p for p in r.json()["providers"]}
    assert providers["ollama"]["needs_api_key"] is False
    assert providers["anthropic"]["needs_api_key"] is True


def test_config_endpoint(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["max_problems"] == 200
    assert body["max_targets"] == 10
    assert body["auth_required"] is False


def test_pricing_endpoint_reports_verification_dates(client):
    r = client.get("/api/pricing")
    assert r.status_code == 200
    body = r.json()
    assert "pricing" in body and "last_verified" in body
    # كل مزوّد له تاريخ تحقّق — حتى لا يظهر سعر قديم كأنه مؤكَّد
    assert set(body["pricing"]) <= set(body["last_verified"])


def test_unknown_benchmark_returns_404(client):
    assert client.get("/api/benchmarks/nope/categories").status_code == 404
    assert client.get("/api/benchmarks/nope/difficulties").status_code == 404
    r = client.post("/api/estimate", json={"benchmark": "nope", "targets": []})
    assert r.status_code == 404


def test_missing_run_returns_404(client):
    assert client.get("/api/runs/deadbeef").status_code == 404
    assert client.get("/api/runs/deadbeef/h2h").status_code == 404
    assert client.delete("/api/runs/deadbeef").status_code == 404
    assert client.get("/api/runs/deadbeef/export").status_code == 404


# ============ التحقّق من المدخلات ============

def test_run_rejects_unknown_provider(client):
    r = client.post("/api/run", json={
        "benchmark": "saudi_legal",
        "targets": [{"provider": "evilcorp", "model": "x", "api_key": "k"}],
    })
    assert r.status_code == 422


def test_run_rejects_empty_targets(client):
    r = client.post("/api/run", json={"benchmark": "saudi_legal", "targets": []})
    assert r.status_code == 422


def test_run_rejects_too_many_targets(client):
    targets = [{"provider": "ollama", "model": f"m{i}"} for i in range(11)]
    r = client.post("/api/run", json={"benchmark": "saudi_legal", "targets": targets})
    assert r.status_code == 422


@pytest.mark.parametrize("n", [0, 201, -5])
def test_run_rejects_out_of_range_n_problems(client, n):
    r = client.post("/api/run", json={
        "benchmark": "saudi_legal",
        "n_problems": n,
        "targets": [{"provider": "ollama", "model": "x"}],
    })
    assert r.status_code == 422


def test_estimate_computes_cost_for_known_model(client):
    r = client.post("/api/estimate", json={
        "benchmark": "saudi_legal",
        "n_problems": 3,
        "targets": [{"provider": "anthropic", "model": "claude-opus-5"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["n_problems_effective"] == 3
    assert body["per_target"][0]["has_price"] is True
    assert body["total_usd"] > 0


def test_estimate_flags_unknown_pricing(client):
    r = client.post("/api/estimate", json={
        "benchmark": "saudi_legal",
        "n_problems": 2,
        "targets": [{"provider": "anthropic", "model": "no-such-model"}],
    })
    assert r.status_code == 200
    assert r.json()["per_target"][0]["has_price"] is False


def test_estimate_handles_empty_filter_result(client):
    r = client.post("/api/estimate", json={
        "benchmark": "saudi_legal",
        "categories": ["تصنيف غير موجود"],
        "targets": [{"provider": "ollama", "model": "x"}],
    })
    assert r.status_code == 200
    assert r.json()["n_problems_effective"] == 0


# ============ حماية SSRF ============

@pytest.mark.parametrize("bad_url", [
    "http://169.254.169.254/latest/meta-data/",
    "file:///etc/passwd",
    "gopher://internal:70/",
])
def test_ollama_endpoint_blocks_unsafe_urls(client, bad_url):
    r = client.get("/api/ollama/models", params={"base_url": bad_url})
    assert r.status_code == 400


def test_run_rejects_unsafe_base_url(client):
    r = client.post("/api/run", json={
        "benchmark": "saudi_legal",
        "targets": [{
            "provider": "ollama", "model": "llama",
            "base_url": "http://169.254.169.254",
        }],
    })
    assert r.status_code == 422


def test_localhost_base_url_is_allowed(client):
    """Ollama المحلي هو الاستخدام المشروع ويجب ألا يُحظر."""
    r = client.get("/api/ollama/models", params={"base_url": "http://127.0.0.1:11434"})
    # الاتصال سيفشل (لا Ollama هنا) لكن العنوان نفسه مقبول
    assert r.status_code == 200
    assert r.json()["error"] is not None


# ============ الرؤوس الأمنية ============

def test_security_headers_present(client):
    r = client.get("/api/benchmarks")
    assert "Content-Security-Policy" in r.headers
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    # السكربتات بلا unsafe-inline هي ما يوقف XSS فعلياً
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"


# ============ المصادقة الاختيارية ============

def test_auth_disabled_by_default(client):
    assert client.get("/api/benchmarks").status_code == 200


def test_auth_enforced_when_token_set(temp_db, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    import backend.main as main

    with TestClient(main.app) as c:
        assert c.get("/api/benchmarks").status_code == 401
        assert c.get("/api/benchmarks", headers={"X-API-Token": "wrong"}).status_code == 401
        assert c.get("/api/benchmarks", headers={"X-API-Token": "s3cret"}).status_code == 200
        assert c.get("/api/config", headers={"X-API-Token": "s3cret"}).json()["auth_required"] is True


def test_auth_protects_destructive_endpoints(temp_db, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    import backend.main as main

    with TestClient(main.app) as c:
        assert c.delete("/api/runs/anything").status_code == 401
        assert c.delete("/api/cache").status_code == 401


# ============ التصدير ============

def _seed_run(db, response_text="hello"):
    run_id = db.create_run("saudi_legal", 1, {})
    db.insert_result(
        run_id, "anthropic", "claude-opus-5", "p1",
        correct=True, raw_score=1.0, latency_ms=12.0,
        input_tokens=5, output_tokens=3, cost_usd=0.001,
        response_text=response_text, judgment="ok",
    )
    db.finish_run(run_id)
    return run_id


def test_export_json_roundtrip(client, temp_db):
    run_id = _seed_run(temp_db)
    r = client.get(f"/api/runs/{run_id}/export", params={"format": "json"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.json()["id"] == run_id


def test_export_csv_neutralizes_formula_injection(client, temp_db):
    """ردّ يبدأ بـ = كان يُفسَّر كصيغة في Excel (التصدير يضيف BOM عمداً)."""
    run_id = _seed_run(temp_db, response_text='=HYPERLINK("http://evil","click")')
    r = client.get(f"/api/runs/{run_id}/export", params={"format": "csv"})
    assert r.status_code == 200
    body = r.text
    assert "'=HYPERLINK" in body
    assert ",=HYPERLINK" not in body


def test_export_rejects_unknown_format(client, temp_db):
    run_id = _seed_run(temp_db)
    assert client.get(f"/api/runs/{run_id}/export", params={"format": "xlsx"}).status_code == 400


def test_delete_run_removes_it(client, temp_db):
    run_id = _seed_run(temp_db)
    assert client.delete(f"/api/runs/{run_id}").status_code == 200
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_cache_stats_and_clear(client, temp_db):
    temp_db.cache_put(
        "k1", "anthropic", "m", text="x", input_tokens=1,
        output_tokens=1, cost_usd=0.5, latency_ms=1.0,
    )
    assert client.get("/api/cache/stats").json()["entries"] == 1
    assert client.delete("/api/cache").json()["cleared"] == 1
    assert client.get("/api/cache/stats").json()["entries"] == 0


# ============ التحقّق من الحَكَم خادمياً ============

def test_run_rejects_llm_judge_without_a_judge(client):
    """كان يُقبَل بـ200، يُنفق كل الاستدعاءات، ثم يُحفظ الـ run بحالة completed."""
    r = client.post("/api/run", json={
        "benchmark": "llm_judge",
        "n_problems": 2,
        "targets": [{"provider": "ollama", "model": "llama3"}],
    })
    assert r.status_code == 400
    assert "حَكَم" in r.json()["detail"]


def test_run_accepts_llm_judge_with_a_judge(client):
    r = client.post("/api/run", json={
        "benchmark": "llm_judge",
        "n_problems": 1,
        "targets": [{"provider": "ollama", "model": "llama3"}],
        "judge": {"provider": "anthropic", "model": "claude-haiku-4-5", "api_key": "k"},
    })
    assert r.status_code == 200


def test_benchmarks_endpoint_exposes_judge_and_code_flags(client):
    by_id = {b["id"]: b for b in client.get("/api/benchmarks").json()["benchmarks"]}
    assert by_id["llm_judge"]["needs_judge"] is True
    assert by_id["humaneval"]["executes_code"] is True


# ============ التفاصيل المقسّمة ============

def _seed_many(db, n=5):
    run_id = db.create_run("saudi_legal", n, {})
    for i in range(n):
        db.insert_result(
            run_id, "anthropic", "claude-opus-5", f"p{i}",
            correct=i % 2 == 0, raw_score=1.0, latency_ms=1.0,
            input_tokens=1, output_tokens=1, cost_usd=0.0,
            response_text=f"رد {i}", judgment="",
        )
    db.insert_result(
        run_id, "openai", "gpt-5-mini", "p0",
        correct=True, raw_score=1.0, latency_ms=1.0,
        input_tokens=1, output_tokens=1, cost_usd=0.0,
        response_text="رد آخر", judgment="",
    )
    db.finish_run(run_id)
    return run_id


def test_run_summary_omits_heavy_details_by_default(client, temp_db):
    """2000 صفّاً بردود 5000 حرف = استجابة تتجاوز 10MB كانت تُطلب ثلاث مرّات."""
    run_id = _seed_many(temp_db)
    body = client.get(f"/api/runs/{run_id}").json()
    assert "details" not in body
    assert body["models"], "الملخّص المجمّع يجب أن يبقى"


def test_run_summary_can_still_include_details_explicitly(client, temp_db):
    run_id = _seed_many(temp_db)
    body = client.get(f"/api/runs/{run_id}", params={"include_details": "true"}).json()
    assert len(body["details"]) == 6


def test_details_endpoint_paginates(client, temp_db):
    run_id = _seed_many(temp_db)
    first = client.get(f"/api/runs/{run_id}/details", params={"limit": 2}).json()
    assert first["total"] == 6
    assert len(first["details"]) == 2

    second = client.get(
        f"/api/runs/{run_id}/details", params={"limit": 2, "offset": 2}
    ).json()
    assert len(second["details"]) == 2
    assert {d["problem_id"] for d in first["details"]} != {
        d["problem_id"] for d in second["details"]
    }


def test_details_endpoint_filters_by_model(client, temp_db):
    run_id = _seed_many(temp_db)
    body = client.get(
        f"/api/runs/{run_id}/details", params={"provider": "openai", "model": "gpt-5-mini"}
    ).json()
    assert body["total"] == 1
    assert body["details"][0]["response_text"] == "رد آخر"


def test_details_endpoint_404s_for_missing_run(client):
    assert client.get("/api/runs/deadbeef/details").status_code == 404


def test_details_endpoint_rejects_absurd_limits(client, temp_db):
    run_id = _seed_many(temp_db)
    assert client.get(f"/api/runs/{run_id}/details", params={"limit": 0}).status_code == 422
    assert client.get(f"/api/runs/{run_id}/details", params={"limit": 5000}).status_code == 422
    assert client.get(f"/api/runs/{run_id}/details", params={"offset": -1}).status_code == 422


# ============ التقدير يسمّي النماذج بلا سعر ============

def test_estimate_names_unpriced_models(client):
    r = client.post("/api/estimate", json={
        "benchmark": "saudi_legal",
        "n_problems": 2,
        "targets": [
            {"provider": "anthropic", "model": "claude-opus-5"},
            {"provider": "cohere", "model": "command-a-03-2025"},
        ],
    })
    body = r.json()
    assert body["unpriced_models"] == ["cohere/command-a-03-2025"]


def test_estimate_reports_no_unpriced_when_all_known(client):
    r = client.post("/api/estimate", json={
        "benchmark": "saudi_legal",
        "n_problems": 2,
        "targets": [{"provider": "anthropic", "model": "claude-opus-5"}],
    })
    assert r.json()["unpriced_models"] == []


# ============ حالة الـ sandbox ============

def test_sandbox_status_note_warns_when_not_isolated(client, monkeypatch):
    monkeypatch.setenv("SANDBOX_BACKEND", "subprocess")
    body = client.get("/api/sandbox/status").json()
    assert body["is_isolated"] is False
    assert "بلا عزل حقيقي" in body["note"]


# ============ تنفيذ الكود بلا عزل يحتاج موافقة صريحة ============

def _unisolated(monkeypatch):
    import backend.main as main
    monkeypatch.setattr(main, "backend_status", lambda: {
        "backend": "subprocess", "docker_available": False,
        "is_isolated": False, "note": "بلا عزل",
    })


def _isolated(monkeypatch):
    import backend.main as main
    monkeypatch.setattr(main, "backend_status", lambda: {
        "backend": "docker", "docker_available": True,
        "is_isolated": True, "note": "معزول",
    })


def test_code_benchmark_is_refused_when_the_sandbox_is_not_isolated(client, monkeypatch):
    """التحذير كان يظهر **بعد** بدء التنفيذ — أي يخبر بما جرى لا بما سيجري."""
    _unisolated(monkeypatch)
    r = client.post("/api/run", json={
        "benchmark": "humaneval",
        "n_problems": 1,
        "targets": [{"provider": "ollama", "model": "llama"}],
    })
    assert r.status_code == 400
    assert "allow_unisolated" in r.json()["detail"]


def test_explicit_consent_allows_the_unisolated_run(client, monkeypatch):
    """الموافقة الواعية تمرّ — لا نمنع من يعرف ما يفعل."""
    _unisolated(monkeypatch)
    r = client.post("/api/run", json={
        "benchmark": "humaneval",
        "n_problems": 1,
        "targets": [{"provider": "ollama", "model": "llama"}],
        "allow_unisolated": True,
    })
    assert r.status_code == 200


def test_isolated_sandbox_needs_no_consent(client, monkeypatch):
    _isolated(monkeypatch)
    r = client.post("/api/run", json={
        "benchmark": "humaneval",
        "n_problems": 1,
        "targets": [{"provider": "ollama", "model": "llama"}],
    })
    assert r.status_code == 200


def test_non_code_benchmarks_are_never_gated_on_the_sandbox(client, monkeypatch):
    """بنشمارك لا ينفّذ كوداً لا علاقة له بالعزل."""
    _unisolated(monkeypatch)
    r = client.post("/api/run", json={
        "benchmark": "saudi_legal",
        "n_problems": 1,
        "targets": [{"provider": "ollama", "model": "llama"}],
    })
    assert r.status_code == 200


# ============ الوصول من خارج الجهاز بلا رمز ============

def _remote_client(temp_db, monkeypatch, **env):
    from fastapi.testclient import TestClient

    monkeypatch.delenv("API_TOKEN", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import backend.main as main
    return TestClient(main.app, client=("192.168.1.50", 5555))


def test_network_request_without_a_token_is_refused(temp_db, monkeypatch):
    """``uvicorn --host 0.0.0.0`` سطرٌ واحد، وبعده يحذف أي جهاز في الشبكة السجل.

    CORS يمنع صفحات المتصفّح لا ``curl``.
    """
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_NETWORK", raising=False)
    with _remote_client(temp_db, monkeypatch) as c:
        r = c.get("/api/benchmarks")
        assert r.status_code == 401
        assert "API_TOKEN" in r.json()["detail"]
        assert c.delete("/api/runs/whatever").status_code == 401


def test_network_access_can_be_opened_deliberately(temp_db, monkeypatch):
    """صمّام لمن يقصد فتحها فعلاً — نمنع الخطأ لا الاختيار."""
    with _remote_client(temp_db, monkeypatch, ALLOW_UNAUTHENTICATED_NETWORK="1") as c:
        assert c.get("/api/benchmarks").status_code == 200


def test_network_access_with_a_token_works_normally(temp_db, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("API_TOKEN", "s3cret")
    import backend.main as main
    with TestClient(main.app, client=("192.168.1.50", 5555)) as c:
        assert c.get("/api/benchmarks").status_code == 401
        r = c.get("/api/benchmarks", headers={"X-API-Token": "s3cret"})
        assert r.status_code == 200


def test_local_requests_stay_frictionless(client):
    """التشغيل المحلي بلا رمز كما كان — لا نُدخل احتكاكاً على الاستخدام المقصود."""
    assert client.get("/api/benchmarks").status_code == 200


# ============ شكل run_id في ترويسة التصدير ============

def test_export_rejects_a_malformed_run_id(client):
    r = client.get('/api/runs/x"; drop/export', params={"format": "json"})
    assert r.status_code == 404
