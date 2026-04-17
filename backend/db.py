"""قاعدة بيانات SQLite لحفظ الـ runs والنتائج."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "benchmarks.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """إنشاء الجداول إذا لم تكن موجودة."""
    with get_conn() as conn:
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
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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
                kwargs.get("response_text", "")[:5000],
                kwargs.get("judgment", "")[:1000],
                kwargs.get("error"),
            ),
        )


def list_runs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.*,
                COUNT(res.id) as n_results,
                AVG(res.raw_score) as avg_score,
                SUM(res.cost_usd) as total_cost
            FROM runs r
            LEFT JOIN results res ON res.run_id = r.id
            GROUP BY r.id
            ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_run(run_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        # تجميع النتائج مع متوسطات لكل (provider, model)
        agg = conn.execute(
            """SELECT provider, model,
                COUNT(*) as n,
                SUM(correct) as n_correct,
                AVG(raw_score) as accuracy,
                AVG(latency_ms) as avg_latency_ms,
                SUM(input_tokens) as total_in_tokens,
                SUM(output_tokens) as total_out_tokens,
                SUM(cost_usd) as total_cost
            FROM results WHERE run_id = ?
            GROUP BY provider, model""",
            (run_id,),
        ).fetchall()
        run["models"] = [dict(r) for r in agg]
        # كل النتائج التفصيلية
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
