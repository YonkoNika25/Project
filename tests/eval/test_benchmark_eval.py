from src.eval.benchmark_eval import evaluate_benchmark_samples
from src.models import (
    BenchmarkMetadata,
    BenchmarkProblem,
    BenchmarkSample,
    DiagnosisLabel,
    ErrorLocalization,
    GoldDiagnosisAnnotation,
    GoldReferenceAnnotation,
    HintLevel,
    GoldHintAnnotation,
    StudentCase,
)


def _make_sample(
    *,
    sample_id: str,
    problem_text: str,
    final_answer: float,
    student_answer_raw: str,
    student_answer_value: float | None,
    label: DiagnosisLabel,
    localization: ErrorLocalization,
    generation_method: str,
) -> BenchmarkSample:
    return BenchmarkSample(
        sample_id=sample_id,
        split="dev_audit",
        source_dataset="gsm8k",
        source_problem_id=sample_id.split("__")[0],
        source_type="synthetic_draft",
        problem=BenchmarkProblem(text=problem_text, difficulty="easy"),
        gold_reference=GoldReferenceAnnotation(
            final_answer=final_answer,
            solution_text=f"#### {int(final_answer)}" if final_answer.is_integer() else f"#### {final_answer}",
        ),
        student_case=StudentCase(
            student_answer_raw=student_answer_raw,
            student_answer_value=student_answer_value,
            error_generation_method=generation_method,
        ),
        gold_diagnosis=GoldDiagnosisAnnotation(
            primary_label=label,
            localization=localization,
            confidence=1.0,
            rationale="Synthetic benchmark case for evaluation harness.",
        ),
        gold_hint=GoldHintAnnotation(
            preferred_level=HintLevel.NEXT_STEP if label == DiagnosisLabel.ARITHMETIC_ERROR else HintLevel.RELATIONAL,
            reference_hints=["Synthetic hint"],
        ) if label != DiagnosisLabel.CORRECT_ANSWER else None,
        metadata=BenchmarkMetadata(created_by="test"),
    )


def test_evaluate_benchmark_samples_reports_diagnosis_and_ablation():
    samples = [
        _make_sample(
            sample_id="gsm8k_train_00000__correct_answer__01",
            problem_text="Juan has 5 apples. He buys 3 more apples. How many apples does he have now?",
            final_answer=8.0,
            student_answer_raw="8",
            student_answer_value=8.0,
            label=DiagnosisLabel.CORRECT_ANSWER,
            localization=ErrorLocalization.NONE,
            generation_method="correct_answer",
        ),
        _make_sample(
            sample_id="gsm8k_train_00001__quantity_relation_error__02",
            problem_text="Lan has 10 candies. She gives 3 candies to her friend. How many candies does she have left?",
            final_answer=7.0,
            student_answer_raw="13",
            student_answer_value=13.0,
            label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
            localization=ErrorLocalization.INTERMEDIATE_STEP,
            generation_method="relation_flip",
        ),
    ]

    summary, audit_entries = evaluate_benchmark_samples(samples, llm_callable=None, run_hints=False)

    assert summary.total_samples == 2
    assert summary.diagnosis_report.correct == 2
    assert summary.diagnosis_report.accuracy == 1.0
    assert summary.localization_report.correct == 2
    assert summary.ablation_report.changed_predictions == 1
    assert summary.ablation_report.improved_cases == 1
    assert summary.confusion_matrix.matrix["correct_answer"]["correct_answer"] == 1
    assert summary.confusion_matrix.matrix["quantity_relation_error"]["quantity_relation_error"] == 1
    assert summary.split_distribution == {"dev_audit": 2}
    assert len(audit_entries) == 2
    assert audit_entries[1]["predicted_label_without_symbolic"] == DiagnosisLabel.UNKNOWN_ERROR.value


def test_evaluate_benchmark_samples_can_run_hint_metrics_without_llm():
    sample = _make_sample(
        sample_id="gsm8k_train_00002__arithmetic_error__01",
        problem_text="Sam has 3 marbles and gets 5 more. How many marbles does he have now?",
        final_answer=8.0,
        student_answer_raw="9",
        student_answer_value=9.0,
        label=DiagnosisLabel.ARITHMETIC_ERROR,
        localization=ErrorLocalization.FINAL_COMPUTATION,
        generation_method="final_step_perturbation",
    )

    summary, audit_entries = evaluate_benchmark_samples([sample], llm_callable=None, run_hints=True)

    assert summary.total_samples == 1
    assert summary.spoiler_free_rate == 1.0
    assert summary.hint_alignment_rate == 1.0
    assert len(audit_entries) == 1
    assert audit_entries[0]["hint_text"] is not None
    assert audit_entries[0]["hint_spoiler_free"] is True
