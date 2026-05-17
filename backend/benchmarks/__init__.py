"""سجل البنشماركات."""
from __future__ import annotations

from backend.benchmarks.arabic_mmlu import ArabicMMLUBenchmark
from backend.benchmarks.base import BaseBenchmark, Problem, Score
from backend.benchmarks.gsm8k import GSM8KBenchmark
from backend.benchmarks.humaneval import HumanEvalBenchmark
from backend.benchmarks.llm_judge import LLMJudgeBenchmark
from backend.benchmarks.mmlu import MMLUBenchmark
from backend.benchmarks.saudi_legal import SaudiLegalBenchmark

BENCHMARKS: dict[str, type[BaseBenchmark]] = {
    "humaneval": HumanEvalBenchmark,
    "gsm8k": GSM8KBenchmark,
    "mmlu": MMLUBenchmark,
    "arabic_mmlu": ArabicMMLUBenchmark,
    "saudi_legal": SaudiLegalBenchmark,
    "llm_judge": LLMJudgeBenchmark,
}


def get_benchmark(name: str) -> BaseBenchmark:
    if name not in BENCHMARKS:
        raise ValueError(f"بنشمارك غير معروف: {name}")
    return BENCHMARKS[name]()


# alias للتوافق مع runner.py
make_benchmark = get_benchmark


_DIFFICULTY_ORDER = ["سهل", "متوسط", "صعب", "easy", "medium", "hard"]


def _sorted_difficulties(values: set[str]) -> list[str]:
    known = [d for d in _DIFFICULTY_ORDER if d in values]
    extras = sorted(values - set(known))
    return known + extras


def list_benchmarks() -> list[dict]:
    """قائمة بالبنشماركات لعرضها في الواجهة."""
    result = []
    for key, cls in BENCHMARKS.items():
        inst = cls()
        try:
            problems = inst.load()
            count = len(problems)
            categories = sorted({p.metadata.get("category") for p in problems if p.metadata.get("category")})
            difficulties = _sorted_difficulties(
                {p.metadata.get("difficulty") for p in problems if p.metadata.get("difficulty")}
            )
        except FileNotFoundError:
            count = 0
            categories = []
            difficulties = []
        result.append({
            "id": key,
            "name": inst.display_name,
            "description": inst.description,
            "problems_count": count,
            "needs_judge": key == "llm_judge",
            "categories": categories,
            "difficulties": difficulties,
        })
    return result


def get_benchmark_categories(name: str) -> list[str]:
    """ارجع تصنيفات البنشمارك إذا كانت موجودة في الـ metadata."""
    if name not in BENCHMARKS:
        raise ValueError(f"بنشمارك غير معروف: {name}")
    inst = BENCHMARKS[name]()
    try:
        problems = inst.load()
    except FileNotFoundError:
        return []
    return sorted({p.metadata.get("category") for p in problems if p.metadata.get("category")})


def get_benchmark_difficulties(name: str) -> list[str]:
    """ارجع مستويات الصعوبة المتوفّرة في البنشمارك."""
    if name not in BENCHMARKS:
        raise ValueError(f"بنشمارك غير معروف: {name}")
    inst = BENCHMARKS[name]()
    try:
        problems = inst.load()
    except FileNotFoundError:
        return []
    return _sorted_difficulties(
        {p.metadata.get("difficulty") for p in problems if p.metadata.get("difficulty")}
    )


__all__ = [
    "BENCHMARKS", "BaseBenchmark", "Problem", "Score",
    "get_benchmark", "make_benchmark", "list_benchmarks",
    "get_benchmark_categories", "get_benchmark_difficulties",
]
