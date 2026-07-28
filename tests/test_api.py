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
