"""Evaluation helpers for benchmark generation, labels, and audit export."""

from src.eval.audit_io import (
    build_audit_review_template,
    load_audit_review_csv,
    load_label_map,
    write_audit_jsonl,
    write_audit_review_csv,
    write_benchmark_jsonl,
)
from src.eval.benchmark_generator import (
    BenchmarkGenerationBundle,
    ProblemSelectionScore,
    generate_benchmark_bundle,
    generate_candidate_samples,
    score_problem_for_benchmark,
    select_base_problems,
)
from src.eval.benchmark_eval import (
    BenchmarkEvalSummary,
    ConfusionMatrixReport,
    LocalizationEvalReport,
    evaluate_benchmark_samples,
    load_benchmark_samples,
)
from src.eval.benchmark_stress import (
    StressGenerationBundle,
    generate_stress_variants,
    make_stress_variant,
)

__all__ = [
    "load_label_map",
    "write_audit_jsonl",
    "write_benchmark_jsonl",
    "build_audit_review_template",
    "write_audit_review_csv",
    "load_audit_review_csv",
    "ProblemSelectionScore",
    "BenchmarkGenerationBundle",
    "score_problem_for_benchmark",
    "select_base_problems",
    "generate_candidate_samples",
    "generate_benchmark_bundle",
    "LocalizationEvalReport",
    "ConfusionMatrixReport",
    "BenchmarkEvalSummary",
    "load_benchmark_samples",
    "evaluate_benchmark_samples",
    "StressGenerationBundle",
    "make_stress_variant",
    "generate_stress_variants",
]
