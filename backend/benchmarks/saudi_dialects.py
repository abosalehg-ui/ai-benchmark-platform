"""بنشمارك اللهجات السعودية - يقيس فهم النموذج للنجدية والحجازية والجنوبية والشرقية."""
from __future__ import annotations

from backend.benchmarks.arabic_mcq import ArabicMCQBenchmark
from backend.benchmarks.base import Problem


class SaudiDialectsBenchmark(ArabicMCQBenchmark):
    name = "saudi_dialects"
    display_name = "اللهجات السعودية"
    description = (
        "يختبر فهم النموذج للهجات السعودية: النجدية، الحجازية، الجنوبية، الشرقية. "
        "معاني المفردات والعبارات الشائعة."
    )
    dataset_file = "saudi_dialects.json"
    extra_metadata_fields = ("dialect",)
    expert_role = "أنت خبير في اللهجات السعودية واللغة العربية الفصحى."

    def _header(self, problem: Problem) -> str:
        dialect = problem.metadata.get("dialect", "")
        return f"اللهجة: {dialect}" if dialect else ""
