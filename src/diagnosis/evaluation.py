"""Diagnosis evaluation utilities for accuracy, calibration, and ablation."""
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

from src.models import DiagnosisLabel, DiagnosisResult

logger = logging.getLogger(__name__)


@dataclass
class DiagnosisEvalEntry:
    """Single evaluation entry comparing predicted vs expected diagnosis."""
    problem_id: str
    predicted: DiagnosisLabel
    expected: Optional[DiagnosisLabel] = None
    match: bool = False


@dataclass
class DiagnosisEvalReport:
    """Aggregate evaluation metrics for diagnosis quality."""
    total: int = 0
    labeled_count: int = 0
    correct: int = 0
    incorrect: int = 0
    unlabeled_count: int = 0
    label_distribution: dict = field(default_factory=dict)
    entries: List[DiagnosisEvalEntry] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if self.labeled_count == 0:
            return 0.0
        return self.correct / self.labeled_count


@dataclass
class CalibrationBin:
    """Per-bin confidence calibration summary."""
    low: float
    high: float
    count: int
    accuracy: float
    avg_confidence: float
    gap: float


@dataclass
class CalibrationReport:
    """Expected calibration error report for diagnosis confidence."""
    labeled_count: int
    num_bins: int
    ece: float
    mce: float
    bins: List[CalibrationBin] = field(default_factory=list)


@dataclass
class AblationReport:
    """Comparison of diagnosis quality with vs without symbolic evidence."""
    labeled_count: int
    with_symbolic_correct: int
    without_symbolic_correct: int
    with_symbolic_accuracy: float
    without_symbolic_accuracy: float
    delta_accuracy: float
    changed_predictions: int
    improved_cases: int
    degraded_cases: int


def evaluate_diagnoses(
    predictions: List[tuple[str, DiagnosisResult]],
    ground_truth: Optional[dict[str, DiagnosisLabel]] = None,
) -> DiagnosisEvalReport:
    """Evaluate diagnosis predictions against optional ground truth."""
    ground_truth = ground_truth or {}
    report = DiagnosisEvalReport(total=len(predictions))

    label_counts = Counter()

    for problem_id, diagnosis in predictions:
        label_counts[diagnosis.label.value] += 1

        expected = ground_truth.get(problem_id)

        if expected is not None:
            report.labeled_count += 1
            match = diagnosis.label == expected
            if match:
                report.correct += 1
            else:
                report.incorrect += 1
            report.entries.append(
                DiagnosisEvalEntry(
                    problem_id=problem_id,
                    predicted=diagnosis.label,
                    expected=expected,
                    match=match,
                )
            )
        else:
            report.unlabeled_count += 1
            report.entries.append(
                DiagnosisEvalEntry(
                    problem_id=problem_id,
                    predicted=diagnosis.label,
                )
            )

    report.label_distribution = dict(label_counts)

    logger.info(
        "Diagnosis evaluation: %d total, %d labeled, %d correct (%.1f%% accuracy)",
        report.total,
        report.labeled_count,
        report.correct,
        report.accuracy * 100,
    )

    return report


def compute_confidence_calibration(
    predictions: List[tuple[str, DiagnosisResult]],
    ground_truth: dict[str, DiagnosisLabel],
    num_bins: int = 5,
) -> CalibrationReport:
    """Compute ECE/MCE for diagnosis confidence over labeled items."""
    if num_bins <= 0:
        raise ValueError("num_bins must be > 0")

    labeled = []
    for pid, pred in predictions:
        expected = ground_truth.get(pid)
        if expected is None:
            continue
        labeled.append((pred.confidence, pred.label == expected))

    if not labeled:
        return CalibrationReport(labeled_count=0, num_bins=num_bins, ece=0.0, mce=0.0, bins=[])

    bins: List[CalibrationBin] = []
    ece = 0.0
    mce = 0.0
    n = len(labeled)

    for i in range(num_bins):
        low = i / num_bins
        high = (i + 1) / num_bins
        members = [x for x in labeled if (low <= x[0] < high) or (i == num_bins - 1 and x[0] == 1.0)]
        if not members:
            bins.append(CalibrationBin(low=low, high=high, count=0, accuracy=0.0, avg_confidence=0.0, gap=0.0))
            continue

        avg_conf = sum(c for c, _ in members) / len(members)
        acc = sum(1 for _, m in members if m) / len(members)
        gap = abs(acc - avg_conf)
        ece += gap * (len(members) / n)
        mce = max(mce, gap)
        bins.append(
            CalibrationBin(
                low=low,
                high=high,
                count=len(members),
                accuracy=acc,
                avg_confidence=avg_conf,
                gap=gap,
            )
        )

    return CalibrationReport(labeled_count=n, num_bins=num_bins, ece=ece, mce=mce, bins=bins)


def compare_symbolic_ablation(
    with_symbolic: List[tuple[str, DiagnosisResult]],
    without_symbolic: List[tuple[str, DiagnosisResult]],
    ground_truth: dict[str, DiagnosisLabel],
) -> AblationReport:
    """Compare diagnosis accuracy with and without symbolic evidence."""
    without_map = {pid: pred for pid, pred in without_symbolic}

    labeled_count = 0
    with_correct = 0
    without_correct = 0
    changed_predictions = 0
    improved = 0
    degraded = 0

    for pid, with_pred in with_symbolic:
        expected = ground_truth.get(pid)
        without_pred = without_map.get(pid)
        if expected is None or without_pred is None:
            continue

        labeled_count += 1
        with_match = with_pred.label == expected
        without_match = without_pred.label == expected
        with_correct += int(with_match)
        without_correct += int(without_match)

        if with_pred.label != without_pred.label:
            changed_predictions += 1
            if with_match and not without_match:
                improved += 1
            elif without_match and not with_match:
                degraded += 1

    with_acc = with_correct / labeled_count if labeled_count else 0.0
    without_acc = without_correct / labeled_count if labeled_count else 0.0

    return AblationReport(
        labeled_count=labeled_count,
        with_symbolic_correct=with_correct,
        without_symbolic_correct=without_correct,
        with_symbolic_accuracy=with_acc,
        without_symbolic_accuracy=without_acc,
        delta_accuracy=with_acc - without_acc,
        changed_predictions=changed_predictions,
        improved_cases=improved,
        degraded_cases=degraded,
    )


def export_audit_log(report: DiagnosisEvalReport) -> List[dict]:
    """Export evaluation entries as structured dicts for error analysis."""
    return [
        {
            "problem_id": e.problem_id,
            "predicted": e.predicted.value,
            "expected": e.expected.value if e.expected else None,
            "match": e.match,
        }
        for e in report.entries
    ]
