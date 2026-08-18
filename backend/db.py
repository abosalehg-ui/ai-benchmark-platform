"""قاعدة بيانات SQLite لحفظ الـ runs والنتائج."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "benchmarks.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> dict:
    """ارجع dict فيه center و margin و lower و upper لفاصل ويلسون عند ثقة 95%.

    أنسب من الفاصل التقليدي للعينات الصغيرة (n<30).
    """
    if n <= 0:
        return {"center": 0.0, "margin": 0.0, "lower": 0.0, "upper": 0.0}
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return {
        "center": center,
        "margin": margin,
        "lower": max(0.0, center - margin),
        "upper": min(1.0, center + margin),
    }


def init_db() -> None:
    """إنشاء الجداول إذا لم تكن موجودة."""
    with get_conn() as conn:
        # WAL يسمح بقراءات متزامنة أثناء الكتابة ويقلّل أخطاء القفل.
        # journal_mode يُخزَّن في ملف القاعدة فيكفي ضبطه مرة واحدة.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            finished_at REAL,
            benchmark TEXT NOT NULL,
            n_problems INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            config_json TEXT
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            problem_id TEXT NOT NULL,
            correct INTEGER NOT NULL,
            raw_score REAL NOT NULL,
            latency_ms REAL NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            response_text TEXT,
            judgment TEXT,
            error TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
        CREATE INDEX IF NOT EXISTS idx_results_model ON results(provider, model);

        CREATE TABLE IF NOT EXISTS response_cache (
            cache_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            response_text TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            latency_ms REAL NOT NULL,
            created_at REAL NOT NULL
        );
        """)


def make_cache_key(
    provider: str,
    model: str,
    prompt: str,
    system: str | None,
    temperature: float,
    max_tokens: int = 2048,
) -> str:
    """مفتاح الـ cache — يشمل كل ما يغيّر الاستجابة.

    ``max_tokens`` جزء من المفتاح لأن الحَكَم يستدعي بـ512 بينما النموذج
    المستهدف بـ2048، وصارا يتشاركان نفس الـ cache: بلا هذا الحقل قد تُرجَّع
    استجابة مقصوصة بحدّ مختلف عن المطلوب.
    """
    payload = json.dumps(
        {"p": provider, "m": model, "q": prompt, "s": system or "", "t": temperature,
         "mt": max_tokens},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_get(key: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM response_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        return dict(row) if row else None


def cache_put(key: str, provider: str, model: str, *, text: str, input_tokens: int,
              output_tokens: int, cost_usd: float, latency_ms: float) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO response_cache
            (cache_key, provider, model, response_text, input_tokens, output_tokens,
             cost_usd, latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, provider, model, text, input_tokens, output_tokens,
             cost_usd, latency_ms, time.time()),
        )


def cache_stats() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS saved_cost FROM response_cache"
        ).fetchone()
        return {"entries": row["n"], "cached_cost_value_usd": round(row["saved_cost"], 6)}


def cache_clear() -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM response_cache")
        return cur.rowcount


_local = threading.local()


@contextmanager
def get_conn():
    """اتصال SQLite لكل خيط، يُعاد استخدامه بدل فتح/إغلاق لكل عملية.

    كان كل استدعاء يفتح اتصالاً جديداً؛ مع 200 مسألة × عدّة نماذج تصبح
    مئات دورات connect/commit/close أثناء البثّ، كلٌّ منها يعيد تحميل
    الـ schema. الاتصال مرتبط بالخيط لأن كائنات sqlite3 ليست thread-safe،
    ويُعاد فتحه تلقائياً إذا تغيّر ``DB_PATH`` (تفعله الاختبارات).
    """
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) != DB_PATH:
        conn.close()
        conn = None
    if conn is None:
        # timeout=30 يمنح مهلة أطول قبل رفع "database is locked" تحت التزامن
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
        _local.path = DB_PATH
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def create_run(benchmark: str, n_problems: int, config: dict) -> str:
    run_id = str(uuid.uuid4())[:8]
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO runs (id, created_at, benchmark, n_problems, status, config_json) "
            "VALUES (?, ?, ?, ?, 'running', ?)",
            (run_id, time.time(), benchmark, n_problems, json.dumps(config)),
        )
    return run_id


def finish_run(run_id: str, status: str = "completed") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
            (time.time(), status, run_id),
        )


def insert_result(run_id: str, provider: str, model: str, problem_id: str, **kwargs) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO results
            (run_id, provider, model, problem_id, correct, raw_score, latency_ms,
             input_tokens, output_tokens, cost_usd, response_text, judgment, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, provider, model, problem_id,
                int(kwargs.get("correct", False)),
                kwargs.get("raw_score", 0.0),
                kwargs.get("latency_ms", 0.0),
                kwargs.get("input_tokens", 0),
                kwargs.get("output_tokens", 0),
                kwargs.get("cost_usd", 0.0),
                # ``or ""`` وليس القيمة الافتراضية وحدها: تمرير None صراحةً
                # يتجاوز الافتراضي ويرفع TypeError فيُسقط الـ run كاملاً
                (kwargs.get("response_text") or "")[:5000],
                (kwargs.get("judgment") or "")[:1000],
                kwargs.get("error"),
            ),
        )


def list_runs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.*,
                COUNT(res.id) as n_results,
                AVG(CAST(res.correct AS REAL)) as avg_score,
                AVG(res.raw_score) as avg_raw_score,
                SUM(res.cost_usd) as total_cost
            FROM runs r
            LEFT JOIN results res ON res.run_id = r.id
            GROUP BY r.id
            ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def run_exists(run_id: str) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is not None


def get_run_details(
    run_id: str,
    *,
    limit: int = 200,
    offset: int = 0,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """صفحة واحدة من نتائج الـ run مع العدد الكلّي.

    كانت ``get_run`` تُرجع كل الصفوف دائماً؛ تشغيل بالحدّ الأقصى (2000 صفّ ×
    ردود حتى 5000 حرف) يتجاوز 10 ميغابايت في استجابة واحدة، وكانت الواجهة
    تطلبها ثلاث مرّات لنفس الـ run.
    """
    where = ["run_id = ?"]
    params: list = [run_id]
    if provider:
        where.append("provider = ?")
        params.append(provider)
    if model:
        where.append("model = ?")
        params.append(model)
    clause = " AND ".join(where)

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM results WHERE {clause}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM results WHERE {clause} ORDER BY id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {
        "run_id": run_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "details": [dict(r) for r in rows],
    }


def get_run(run_id: str, include_details: bool = False) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        # تجميع النتائج مع متوسطات لكل (provider, model)
        # ملاحظة مهمّة: ``accuracy`` مشتقّة من ``correct`` الثنائية حتى تكون
        # من نفس الكمية التي يُحسب منها فاصل ويلسون. ``avg_raw_score`` مقياس
        # منفصل ومستمر (tool_use يعطي 0.5، llm_judge يعطي 0.25/0.5/0.75)
        # وكان خلطه مع الفاصل يعرض «78.5% ± 12.3» من مقياسين مختلفين.
        agg = conn.execute(
            """SELECT provider, model,
                COUNT(*) as n,
                SUM(correct) as n_correct,
                AVG(CAST(correct AS REAL)) as accuracy,
                AVG(raw_score) as avg_raw_score,
                AVG(latency_ms) as avg_latency_ms,
                SUM(input_tokens) as total_in_tokens,
                SUM(output_tokens) as total_out_tokens,
                SUM(cost_usd) as total_cost
            FROM results WHERE run_id = ?
            GROUP BY provider, model""",
            (run_id,),
        ).fetchall()
        run["models"] = []
        for r in agg:
            d = dict(r)
            ci = wilson_interval(int(d.get("n_correct") or 0), int(d.get("n") or 0))
            d["ci_lower"] = ci["lower"]
            d["ci_upper"] = ci["upper"]
            d["ci_margin"] = ci["margin"]
            run["models"].append(d)
        # التفاصيل ثقيلة ولا يحتاجها الملخّص — تُطلب من ``get_run_details``
        # المقسّم، أو هنا صراحةً عند التصدير الكامل
        if include_details:
            details = conn.execute(
                "SELECT * FROM results WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
            run["details"] = [dict(r) for r in details]
        return run


def delete_run(run_id: str) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM results WHERE run_id = ?", (run_id,))
        cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        return cur.rowcount > 0


def head_to_head(run_id: str) -> dict | None:
    """يحسب مصفوفة المقارنة الزوجية بين النماذج في run معين.

    لكل زوج (A, B) من النماذج، يحسب على المسائل المشتركة:
    - both_correct: كلاهما أصاب
    - a_only: A أصاب وحده
    - b_only: B أصاب وحده
    - both_wrong: كلاهما أخطأ
    - a_wins: نسبة المسائل التي تفوّق فيها A وحده
    - n_compared: عدد المسائل المشتركة
    """
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone():
            return None
        rows = conn.execute(
            "SELECT provider, model, problem_id, correct FROM results WHERE run_id = ?",
            (run_id,),
        ).fetchall()

    by_model: dict[tuple[str, str], dict[str, bool]] = {}
    for r in rows:
        key = (r["provider"], r["model"])
        by_model.setdefault(key, {})[r["problem_id"]] = bool(r["correct"])

    models = sorted(by_model.keys())
    matrix: list[list[dict]] = []
    for a in models:
        row: list[dict] = []
        a_results = by_model[a]
        for b in models:
            b_results = by_model[b]
            both_c = a_only = b_only = both_w = 0
            for pid, a_corr in a_results.items():
                if pid not in b_results:
                    continue
                b_corr = b_results[pid]
                if a_corr and b_corr:
                    both_c += 1
                elif a_corr and not b_corr:
                    a_only += 1
                elif b_corr and not a_corr:
                    b_only += 1
                else:
                    both_w += 1
            n = both_c + a_only + b_only + both_w
            row.append({
                "both_correct": both_c,
                "a_only": a_only,
                "b_only": b_only,
                "both_wrong": both_w,
                "n_compared": n,
                "a_wins_pct": round((a_only / n) * 100, 1) if n else 0.0,
            })
        matrix.append(row)

    return {
        "models": [{"provider": p, "model": m} for p, m in models],
        "matrix": matrix,
    }
