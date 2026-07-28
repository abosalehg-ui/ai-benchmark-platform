"""فلترة المسائل حسب التصنيف والصعوبة.

كانت هذه الدالة تعيش في ``runner.py`` باسم خاص ``_filter_problems`` ويستوردها
``main.py`` عبر حدود الوحدات — عقد ضمني تكسره أي إعادة تسمية. نقلناها إلى
وحدة عامة يستوردها الطرفان.
"""
from __future__ import annotations

from backend.benchmarks.base import Problem


def filter_problems(
    problems: list[Problem],
    categories: list[str],
    difficulties: list[str],
) -> list[Problem]:
    """ارجع المسائل المطابقة للفلاتر. قائمة فارغة = بلا فلترة."""
    out = problems
    if categories:
        wanted = set(categories)
        out = [p for p in out if p.metadata.get("category") in wanted]
    if difficulties:
        wanted = set(difficulties)
        out = [p for p in out if p.metadata.get("difficulty") in wanted]
    return out
