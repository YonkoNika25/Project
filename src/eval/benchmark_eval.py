"""Benchmark evaluation harness for curated benchmark samples."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.checker.answer_checker import check_answer
from src.diagnosis.engine import diagnose
from src.diagnosis.evaluation import (
    AblationReport,
    CalibrationReport,
    DiagnosisEvalReport,
    compare_symbolic_ablation,
    compute_confidence_calibration,
    evaluate_diagnoses,
)
from src.hint.controller import HintController
from src.hint.verifier import verify_hint_alignment, verify_hint_no_spoiler
from src.models import BenchmarkSample, DiagnosisLabel, DiagnosisResult, ErrorLocalization
from src.verification.symbolic_state_builder import build_symbolic_state
from src.verification.symbolic_verifier import verify_symbolic_consistency


@dataclass
class LocalizationEvalReport:
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return self.correct / self.total


@dataclass
class ConfusionMatrixReport:
    labels: list[str]
    matrix: dict[str, dict[str, int]]


@dataclass
class BenchmarkEvalSummary:
    total_samples: int
    diagnosis_report: DiagnosisEvalReport
    localization_report: LocalizationEvalReport
    calibration_report: CalibrationReport
    ablation_report: AblationReport
    confusion_matrix: ConfusionMatrixReport
    spoiler_free_rate: float
    hint_alignment_rate: float
    hint_fallback_rate: float
    verification_status_distribution: dict[str, int]
    split_distribution: dict[str, int]


def load_benchmark_samples(path: str) -> list[BenchmarkSample]:
    """Load benchmark samples from JSONL."""
    rows: list[BenchmarkSample] = []
    p = Path(path)
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(BenchmarkSample.model_validate(json.loads(line)))
    return rows


def _evaluate_localization(
    predictions: Iterable[tuple[str, DiagnosisResult]],
    ground_truth: dict[str, ErrorLocalization],
) -> LocalizationEvalReport:
    total = 0
    correct = 0
    for sample_id, diagnosis in predictions:
        expected = ground_truth.get(sample_id)
        if expected is None:
            continue
        total += 1
        if diagnosis.localization == expected:
            correct += 1
    return LocalizationEvalReport(total=total, correct=correct)


def _build_confusion_matrix(
    predictions: Iterable[tuple[str, DiagnosisResult]],
    ground_truth: dict[str, DiagnosisLabel],
) -> ConfusionMatrixReport:
    labels = [label.value for label in DiagnosisLabel]
    matrix = {
        gold: {pred: 0 for pred in labels}
        for gold in labels
    }

    for sample_id, diagnosis in predictions:
        gold_label = ground_truth.get(sample_id)
        if gold_label is None:
            continue
        matrix[gold_label.value][diagnosis.label.value] += 1

    return ConfusionMatrixReport(labels=labels, matrix=matrix)


def evaluate_benchmark_samples(
    samples: list[BenchmarkSample],
    llm_callable=None,
    run_hints: bool = True,
) -> tuple[BenchmarkEvalSummary, list[dict]]:
    """Run diagnosis/hint evaluation on curated benchmark samples."""
    predictions_with_symbolic: list[tuple[str, DiagnosisResult]] = []
    predictions_without_symbolic: list[tuple[str, DiagnosisResult]] = []
    audit_entries: list[dict] = []
    verification_counter: Counter[str] = Counter()
    split_counter: Counter[str] = Counter()

    spoiler_free = 0
    hint_alignment_ok = 0
    hint_fallback_count = 0

    hint_controller = HintController(llm_callable=llm_callable)

    ground_truth_labels = {
        sample.sample_id: sample.gold_diagnosis.primary_label
        for sample in samples
    }
    ground_truth_localizations = {
        sample.sample_id: sample.gold_diagnosis.localization
        for sample in samples
    }

    for sample in samples:
        split_counter[sample.split] += 1
        check_result = check_answer(
            sample.student_case.student_answer_raw,
            sample.gold_reference.final_answer,
        )
        symbolic_state = build_symbolic_state(
            sample.problem.text,
            sample.gold_reference.solution_text,
        )
        verification_result = verify_symbolic_consistency(symbolic_state, check_result)
        verification_counter[verification_result.status.value] += 1

        diagnosis_with_symbolic = diagnose(
            problem_text=sample.problem.text,
            reference_solution_text=sample.gold_reference.solution_text,
            reference_answer=sample.gold_reference.final_answer,
            student_raw=sample.student_case.student_answer_raw,
            check_result=check_result,
            llm_callable=llm_callable,
            symbolic_state=symbolic_state,
            verification_result=verification_result,
        )
        diagnosis_without_symbolic = diagnose(
            problem_text=sample.problem.text,
            reference_solution_text=sample.gold_reference.solution_text,
            reference_answer=sample.gold_reference.final_answer,
            student_raw=sample.student_case.student_answer_raw,
            check_result=check_result,
            llm_callable=llm_callable,
            symbolic_state=None,
            verification_result=None,
        )

        predictions_with_symbolic.append((sample.sample_id, diagnosis_with_symbolic))
        predictions_without_symbolic.append((sample.sample_id, diagnosis_without_symbolic))

        hint_result = None
        spoiler_ok = None
        alignment_ok = None
        if run_hints:
            hint_result = hint_controller.get_hint(
                problem_text=sample.problem.text,
                reference_solution_text=sample.gold_reference.solution_text,
                reference_answer=sample.gold_reference.final_answer,
                student_raw=sample.student_case.student_answer_raw,
                diagnosis=diagnosis_with_symbolic,
                verification_result=verification_result,
            )
            spoiler_ok = verify_hint_no_spoiler(
                hint_result.hint_text,
                sample.gold_reference.final_answer,
            )
            alignment_ok = verify_hint_alignment(
                hint_result.hint_text,
                diagnosis_label=diagnosis_with_symbolic.label,
                expected_level=hint_result.hint_level,
                diagnosis_localization=diagnosis_with_symbolic.localization,
            )
            spoiler_free += int(spoiler_ok)
            hint_alignment_ok += int(alignment_ok)
            hint_fallback_count += int(hint_result.fallback_used)

        audit_entries.append(
            {
                "sample_id": sample.sample_id,
                "split": sample.split,
                "gold_label": sample.gold_diagnosis.primary_label.value,
                "predicted_label": diagnosis_with_symbolic.label.value,
                "predicted_label_without_symbolic": diagnosis_without_symbolic.label.value,
                "gold_localization": sample.gold_diagnosis.localization.value,
                "predicted_localization": diagnosis_with_symbolic.localization.value,
                "predicted_localization_without_symbolic": diagnosis_without_symbolic.localization.value,
                "diagnosis_match": diagnosis_with_symbolic.label == sample.gold_diagnosis.primary_label,
                "diagnosis_match_without_symbolic": diagnosis_without_symbolic.label == sample.gold_diagnosis.primary_label,
                "localization_match": diagnosis_with_symbolic.localization == sample.gold_diagnosis.localization,
                "diagnosis_confidence": diagnosis_with_symbolic.confidence,
                "diagnosis_confidence_without_symbolic": diagnosis_without_symbolic.confidence,
                "verification_status": verification_result.status.value,
                "verification_label": (
                    verification_result.predicted_label.value if verification_result.predicted_label else None
                ),
                "verification_confidence": verification_result.confidence,
                "gold_hint_level": (
                    sample.gold_hint.preferred_level.value if sample.gold_hint is not None else None
                ),
                "hint_text": hint_result.hint_text if hint_result else None,
                "hint_level": hint_result.hint_level.value if hint_result else None,
                "hint_fallback_used": hint_result.fallback_used if hint_result else None,
                "hint_spoiler_free": spoiler_ok,
                "hint_alignment_ok": alignment_ok,
            }
        )

    diagnosis_report = evaluate_diagnoses(predictions_with_symbolic, ground_truth_labels)
    localization_report = _evaluate_localization(predictions_with_symbolic, ground_truth_localizations)
    calibration_report = compute_confidence_calibration(predictions_with_symbolic, ground_truth_labels)
    ablation_report = compare_symbolic_ablation(
        with_symbolic=predictions_with_symbolic,
        without_symbolic=predictions_without_symbolic,
        ground_truth=ground_truth_labels,
    )
    confusion_matrix = _build_confusion_matrix(predictions_with_symbolic, ground_truth_labels)

    total = len(samples)
    summary = BenchmarkEvalSummary(
        total_samples=total,
        diagnosis_report=diagnosis_report,
        localization_report=localization_report,
        calibration_report=calibration_report,
        ablation_report=ablation_report,
        confusion_matrix=confusion_matrix,
        spoiler_free_rate=(spoiler_free / total) if run_hints and total else 0.0,
        hint_alignment_rate=(hint_alignment_ok / total) if run_hints and total else 0.0,
        hint_fallback_rate=(hint_fallback_count / total) if run_hints and total else 0.0,
        verification_status_distribution=dict(verification_counter),
        split_distribution=dict(split_counter),
    )
    return summary, audit_entries
