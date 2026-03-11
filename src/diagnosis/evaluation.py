"""Diagnosis evaluation: measures quality of baseline diagnosis on a labeled subset."""
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


def evaluate_diagnoses(
    predictions: List[tuple[str, DiagnosisResult]],
    ground_truth: Optional[dict[str, DiagnosisLabel]] = None,
) -> DiagnosisEvalReport:
    """Evaluate diagnosis predictions against optional ground truth.

    Args:
        predictions: List of (problem_id, DiagnosisResult) tuples.
        ground_truth: Optional dict of problem_id -> expected DiagnosisLabel.

    Returns:
        DiagnosisEvalReport with metrics and detailed entries.
    """
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
            report.entries.append(DiagnosisEvalEntry(
                problem_id=problem_id,
                predicted=diagnosis.label,
                expected=expected,
                match=match,
            ))
        else:
            report.unlabeled_count += 1
            report.entries.append(DiagnosisEvalEntry(
                problem_id=problem_id,
                predicted=diagnosis.label,
            ))

    report.label_distribution = dict(label_counts)

    logger.info(
        "Diagnosis evaluation: %d total, %d labeled, %d correct (%.1f%% accuracy)",
        report.total, report.labeled_count, report.correct,
        report.accuracy * 100,
    )

    return report


def export_audit_log(report: DiagnosisEvalReport) -> List[dict]:
    """Export evaluation entries as structured dicts for error analysis.

    Returns:
        List of dicts suitable for JSON export.
    """
    return [
        {
            "problem_id": e.problem_id,
            "predicted": e.predicted.value,
            "expected": e.expected.value if e.expected else None,
            "match": e.match,
        }
        for e in report.entries
    ]
