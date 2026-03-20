from src.eval.benchmark_stress import generate_stress_variants, make_stress_variant
from src.models import (
    BenchmarkMetadata,
    BenchmarkProblem,
    BenchmarkSample,
    DiagnosisLabel,
    ErrorLocalization,
    GoldDiagnosisAnnotation,
    GoldReferenceAnnotation,
    StudentCase,
)


def _make_sample(problem_text: str, student_answer_raw: str) -> BenchmarkSample:
    return BenchmarkSample(
        sample_id="gsm8k_train_00001__quantity_relation_error__03",
        split="dev_audit",
        source_dataset="gsm8k",
        source_problem_id="gsm8k_train_00001",
        source_type="synthetic_draft",
        problem=BenchmarkProblem(text=problem_text, difficulty="easy"),
        gold_reference=GoldReferenceAnnotation(final_answer=7.0, solution_text="#### 7"),
        student_case=StudentCase(
            student_answer_raw=student_answer_raw,
            student_answer_value=13.0,
            error_generation_method="relation_flip",
        ),
        gold_diagnosis=GoldDiagnosisAnnotation(
            primary_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
            localization=ErrorLocalization.COMBINING_QUANTITIES,
            confidence=0.9,
            rationale="Synthetic test sample.",
        ),
        metadata=BenchmarkMetadata(created_by="test", tags=["seed"]),
    )


def test_make_stress_variant_changes_surface_but_preserves_gold_annotations():
    sample = _make_sample(
        "Lan has 10 candies. She gives 3 candies to her friend. How many candies does she have left?",
        "I think the answer is 13.",
    )

    stressed, variant_name = make_stress_variant(sample)

    assert stressed.sample_id.endswith("__stress")
    assert stressed.gold_diagnosis.primary_label == sample.gold_diagnosis.primary_label
    assert stressed.gold_diagnosis.localization == sample.gold_diagnosis.localization
    assert stressed.problem.text != sample.problem.text
    assert stressed.student_case.student_answer_raw != sample.student_case.student_answer_raw
    assert "stress_eval" in stressed.metadata.tags
    assert variant_name


def test_generate_stress_variants_returns_parallel_bundle():
    samples = [
        _make_sample(
            "Juan has 5 apples. She buys 3 more apples. How many apples does she have in all?",
            "I think the answer is 8.",
        ),
        _make_sample(
            "Tom starts with 10 marbles. He gives away 4 marbles. How many marbles are left?",
            "I think the answer is 6.",
        ),
    ]

    bundle = generate_stress_variants(samples)

    assert len(bundle.original_samples) == 2
    assert len(bundle.stressed_samples) >= 6
    assert len(bundle.variant_names) == len(bundle.stressed_samples)
    assert len(bundle.variant_cases) == len(bundle.stressed_samples)
    families = {case.variant_family for case in bundle.variant_cases}
    assert "combined_surface" in families
    assert "answer_format" in families
    assert any(sample.sample_id.endswith("__stress") for sample in bundle.stressed_samples)
