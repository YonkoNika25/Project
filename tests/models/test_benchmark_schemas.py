from src.models import (
    BenchmarkMetadata,
    BenchmarkProblem,
    BenchmarkQuantityAnnotation,
    BenchmarkSample,
    DiagnosisLabel,
    ErrorLocalization,
    GoldDiagnosisAnnotation,
    GoldReferenceAnnotation,
    OperationType,
    StudentCase,
    SymbolicAnnotation,
)


def test_benchmark_sample_valid():
    sample = BenchmarkSample(
        sample_id="gsm8k_train_00001__arithmetic_error__01",
        split="dev_audit",
        source_dataset="gsm8k",
        source_problem_id="gsm8k_train_00001",
        source_type="synthetic_draft",
        problem=BenchmarkProblem(
            text="Lan has 10 candies. She gives 3 away. How many are left?",
            difficulty="easy",
            requires_multi_step=False,
        ),
        gold_reference=GoldReferenceAnnotation(
            final_answer=7.0,
            solution_text="10 - 3 = 7\n#### 7",
            answer_format="integer",
            answer_span="7",
        ),
        student_case=StudentCase(
            student_answer_raw="I think the answer is 8.",
            student_answer_value=8.0,
            error_generation_method="near_miss_final_computation",
        ),
        gold_diagnosis=GoldDiagnosisAnnotation(
            primary_label=DiagnosisLabel.ARITHMETIC_ERROR,
            localization=ErrorLocalization.FINAL_COMPUTATION,
            confidence=0.85,
            rationale="Student stays near the correct result but misses the final computation.",
        ),
        symbolic_annotation=SymbolicAnnotation(
            quantities=[
                BenchmarkQuantityAnnotation(
                    value=10.0,
                    surface_text="10",
                    role="initial_quantity",
                    provenance="problem_text",
                ),
                BenchmarkQuantityAnnotation(
                    value=3.0,
                    surface_text="3",
                    role="removed_quantity",
                    provenance="problem_text",
                ),
            ],
            target_text="How many are left",
            target_type="remaining_quantity",
            expected_relation="subtractive_comparison",
            expected_operation=OperationType.SUBTRACTIVE,
        ),
        metadata=BenchmarkMetadata(
            created_by="benchmark_generator",
            review_status="draft",
            notes="Synthetic benchmark draft.",
            tags=["arithmetic_error"],
        ),
    )

    assert sample.gold_diagnosis.primary_label == DiagnosisLabel.ARITHMETIC_ERROR
    assert sample.symbolic_annotation.expected_operation == OperationType.SUBTRACTIVE
