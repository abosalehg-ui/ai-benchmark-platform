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
        except FileNotFoundError:
            count = 0
        result.append({
            "id": key,
            "name": inst.display_name,
            "description": inst.description,
            "problems_count": count,
            "needs_judge": key == "llm_judge",
        })
    return result


__all__ = ["BENCHMARKS", "BaseBenchmark", "Problem", "Score", "get_benchmark", "make_benchmark", "list_benchmarks"]
