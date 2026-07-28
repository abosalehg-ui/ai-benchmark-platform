"""بنشمارك ArabicMMLU — أسئلة متعددة الخيارات بالعربية."""
from __future__ import annotations

from backend.benchmarks.arabic_mcq import ArabicMCQBenchmark
from backend.benchmarks.base import Problem


class ArabicMMLUBenchmark(ArabicMCQBenchmark):
    name = "arabic_mmlu"
    display_name = "ArabicMMLU (لغة عربية)"
    description = "أسئلة متعددة الخيارات بالعربية في تخصصات متنوعة."
    dataset_file = "arabic_mmlu_sample.json"
    extra_metadata_fields = ("subject",)
    expert_role = "أنت خبير في تخصصات متنوعة."
    # الداتاست بلا تصنيف/صعوبة/شرح — نتركها غائبة حتى لا تعرض الواجهة
    # فلاتر فارغة، وحتى لا يتغيّر شكل /api/benchmarks
    default_category = None
    default_difficulty = None
    show_explanation_on_error = False

    def _header(self, problem: Problem) -> str:
        subject = problem.metadata.get("subject", "")
        return f"التخصّص: {subject}" if subject and subject != "general" else ""
