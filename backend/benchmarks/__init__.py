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


def list_benchmarks() -> list[dict]:
    """قائمة بالبنشماركات لعرضها في الواجهة."""
    result = []
    for key, cls in BENCHMARKS.items():
        inst = cls()
        try:
            problems = inst.load()
            count = len(problems)
            categories = sorted({p.metadata.get("category") for p in problems if p.metadata.get("category")})
        except FileNotFoundError:
            count = 0
            categories = []
        result.append({
            "id": key,
            "name": inst.display_name,
            "description": inst.description,
            "problems_count": count,
            "needs_judge": key == "llm_judge",
            "categories": categories,
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


__all__ = [
    "BENCHMARKS", "BaseBenchmark", "Problem", "Score",
    "get_benchmark", "make_benchmark", "list_benchmarks", "get_benchmark_categories",
]
