"""تتبّع انحراف النماذج عبر الزمن (drift tracking).

**لماذا:** المزوّدون يحدّثون النماذج خلف نفس اسم الإصدار أحياناً بلا إشعار،
فدقّة ``claude-opus-5`` اليوم قد تختلف عنها بعد شهر على نفس البنشمارك. المنصّة
كانت تحفظ كل تشغيل في السجل لكن كجزيرة منفصلة: لا شيء يربط تشغيلات نفس
(بنشمارك، نموذج) ليُظهر الاتجاه.

**المزلق الذي تتجنّبه هذه الوحدة:** مقارنة تشغيل من 10 مسائل بتشغيل من 200
مسألة — أو تشغيلاً مفلتراً على «نظام العمل» بتشغيل بلا فلاتر — ثم تسمية الفرق
«انحرافاً». الفرق هنا من اختلاف العيّنة لا من تغيّر النموذج. لذلك:

1. كل نقطة تحمل ``scope_key``: بصمة (عدد المسائل + التصنيفات + الصعوبات).
2. ``latest_change`` يُحسب **فقط** بين آخر نقطتين تتشاركان نفس البصمة.
3. ``mixed_scopes`` يُرفع للواجهة لتحذّر المستخدم أن السلسلة تخلط نطاقات.

**الدلالة الإحصائية:** نستخدم عدم تداخل فاصلَي ويلسون كاختبار محافظ. هو أقلّ
حساسية من اختبار الفرق بين نسبتين، لكنه لا يُنتج «انحرافاً» وهمياً من عيّنات
صغيرة — وهو ما يهمّ هنا: إنذار كاذب يدفع المستخدم لتغيير نموذج بلا سبب.
"""
from __future__ import annotations

import json

from backend.db import get_conn, wilson_interval


def _scope(config_json: str | None, n_results: int) -> tuple[str, str]:
    """بصمة النطاق ووصفه العربي.

    تعتمد على الفلاتر وعدد المسائل الفعلي: تشغيلان بنفس البصمة قابلان
    للمقارنة، وأي اختلاف يعني أن الفرق قد يكون من العيّنة لا من النموذج.
    """
    try:
        config = json.loads(config_json) if config_json else {}
    except (json.JSONDecodeError, TypeError):
        config = {}

    categories = sorted(config.get("categories") or [])
    difficulties = sorted(config.get("difficulties") or [])
    key = json.dumps(
        {"n": n_results, "c": categories, "d": difficulties},
        ensure_ascii=False, sort_keys=True,
    )

    parts = [f"{n_results} مسألة"]
    parts.append("، ".join(categories) if categories else "كل التصنيفات")
    if difficulties:
        parts.append("، ".join(difficulties))
    return key, " · ".join(parts)


def _significant(a: dict, b: dict) -> bool:
    """هل الفرق بين نقطتين ذو دلالة؟ اختبار محافظ: فاصلا ويلسون لا يتداخلان."""
    return a["ci_upper"] < b["ci_lower"] or b["ci_upper"] < a["ci_lower"]


def drift_series(
    benchmark: str,
    *,
    include_partial: bool = False,
    max_runs: int = 50,
) -> dict:
    """سلاسل الدقّة والتكلفة عبر الزمن لكل نموذج في بنشمارك واحد.

    ``include_partial``: التشغيلات المتوقّفة (ميزانية أو انقطاع) ناقصة العيّنة،
    فهي مستبعَدة افتراضياً — إدراجها يُظهر هبوطاً وهمياً في الدقّة.
    """
    # ``completed_with_errors`` تشغيل مكتمل العيّنة للنماذج التي نجحت — نموذج
    # واحد تعثّر لا يُخرج البقيّة من التتبّع. النماذج المتعثّرة تحمل عدد نتائج
    # مختلفاً، و``scope_key`` (وفيه عدد المسائل) يمنع مقارنتها بتشغيل كامل.
    status_clause = (
        "" if include_partial
        else " AND r.status IN ('completed', 'completed_with_errors')"
    )

    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT r.id AS run_id, r.created_at, r.config_json, r.status,
                       res.provider, res.model,
                       COUNT(*) AS n,
                       SUM(res.correct) AS n_correct,
                       AVG(res.raw_score) AS avg_raw_score,
                       AVG(res.latency_ms) AS avg_latency_ms,
                       SUM(res.cost_usd) AS total_cost
                FROM runs r
                JOIN results res ON res.run_id = r.id
                WHERE r.benchmark = ?{status_clause}
                GROUP BY r.id, res.provider, res.model
                ORDER BY r.created_at ASC""",
            (benchmark,),
        ).fetchall()

    by_model: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        n = int(row["n"] or 0)
        n_correct = int(row["n_correct"] or 0)
        ci = wilson_interval(n_correct, n)
        scope_key, scope_label = _scope(row["config_json"], n)
        by_model.setdefault((row["provider"], row["model"]), []).append({
            "run_id": row["run_id"],
            "created_at": row["created_at"],
            "status": row["status"],
            "n": n,
            "n_correct": n_correct,
            "accuracy": n_correct / n if n else 0.0,
            "avg_raw_score": row["avg_raw_score"] or 0.0,
            "ci_lower": ci["lower"],
            "ci_upper": ci["upper"],
            "ci_margin": ci["margin"],
            "avg_latency_ms": round(row["avg_latency_ms"] or 0.0, 1),
            "total_cost": round(row["total_cost"] or 0.0, 6),
            "scope_key": scope_key,
            "scope_label": scope_label,
        })

    series = []
    for (provider, model), points in sorted(by_model.items()):
        points = points[-max_runs:]
        scopes = {p["scope_key"] for p in points}
        series.append({
            "provider": provider,
            "model": model,
            "points": points,
            "n_runs": len(points),
            "mixed_scopes": len(scopes) > 1,
            "latest_change": _latest_change(points),
        })

    # النماذج ذات التشغيل الواحد لا تُظهر اتجاهاً، لكن نُبقيها ونُعلمها
    return {
        "benchmark": benchmark,
        "series": series,
        "n_models": len(series),
        "trackable": [s for s in series if s["n_runs"] >= 2],
    }


def _latest_change(points: list[dict]) -> dict | None:
    """الفرق بين آخر نقطتين **متطابقتَي النطاق**.

    الرجوع إلى الوراء بحثاً عن نظير قابل للمقارنة أصدق من مقارنة آخر نقطتين
    مهما اختلف نطاقهما: تشغيل 10 مسائل بعد تشغيل 200 ليس انحرافاً.
    """
    if len(points) < 2:
        return None

    latest = points[-1]
    previous = next(
        (p for p in reversed(points[:-1]) if p["scope_key"] == latest["scope_key"]),
        None,
    )
    if previous is None:
        return None

    delta = latest["accuracy"] - previous["accuracy"]
    return {
        "from_run": previous["run_id"],
        "to_run": latest["run_id"],
        "from_accuracy": previous["accuracy"],
        "to_accuracy": latest["accuracy"],
        "delta": delta,
        "delta_pct_points": round(delta * 100, 1),
        "significant": _significant(previous, latest),
        "scope_label": latest["scope_label"],
        "days_apart": round(
            (latest["created_at"] - previous["created_at"]) / 86400, 2
        ),
    }
