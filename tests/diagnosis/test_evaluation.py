import pytest
from src.models import DiagnosisLabel, DiagnosisResult, ErrorLocalization
from src.diagnosis.evaluation import (
    evaluate_diagnoses,
    export_audit_log,
    compute_confidence_calibration,
    compare_symbolic_ablation,
)


def _diag(label: DiagnosisLabel, confidence: float = 0.8) -> DiagnosisResult:
    return DiagnosisResult(
        label=label,
        localization=ErrorLocalization.UNKNOWN,
        explanation="test",
        confidence=confidence,
    )


class TestEvaluateDiagnoses:
    def test_all_correct(self):
        predictions = [
            ("p1", _diag(DiagnosisLabel.ARITHMETIC_ERROR)),
            ("p2", _diag(DiagnosisLabel.CORRECT_ANSWER)),
        ]
        ground_truth = {
            "p1": DiagnosisLabel.ARITHMETIC_ERROR,
            "p2": DiagnosisLabel.CORRECT_ANSWER,
        }
        report = evaluate_diagnoses(predictions, ground_truth)
        assert report.total == 2
        assert report.labeled_count == 2
        assert report.correct == 2
        assert report.accuracy == 1.0

    def test_mixed_results(self):
        predictions = [
            ("p1", _diag(DiagnosisLabel.ARITHMETIC_ERROR)),
            ("p2", _diag(DiagnosisLabel.UNKNOWN_ERROR)),
        ]
        ground_truth = {
            "p1": DiagnosisLabel.ARITHMETIC_ERROR,
            "p2": DiagnosisLabel.QUANTITY_RELATION_ERROR,
        }
        report = evaluate_diagnoses(predictions, ground_truth)
        assert report.correct == 1
        assert report.incorrect == 1
        assert report.accuracy == 0.5

    def test_no_ground_truth(self):
        predictions = [
            ("p1", _diag(DiagnosisLabel.ARITHMETIC_ERROR)),
            ("p2", _diag(DiagnosisLabel.CORRECT_ANSWER)),
        ]
        report = evaluate_diagnoses(predictions)
        assert report.total == 2
        assert report.unlabeled_count == 2
        assert report.accuracy == 0.0

    def test_label_distribution(self):
        predictions = [
            ("p1", _diag(DiagnosisLabel.ARITHMETIC_ERROR)),
            ("p2", _diag(DiagnosisLabel.ARITHMETIC_ERROR)),
            ("p3", _diag(DiagnosisLabel.CORRECT_ANSWER)),
        ]
        report = evaluate_diagnoses(predictions)
        assert report.label_distribution["arithmetic_error"] == 2
        assert report.label_distribution["correct_answer"] == 1

    def test_empty_predictions(self):
        report = evaluate_diagnoses([])
        assert report.total == 0
        assert report.accuracy == 0.0


class TestConfidenceCalibration:
    def test_calibration_metrics_non_zero(self):
        predictions = [
            ("p1", _diag(DiagnosisLabel.ARITHMETIC_ERROR, confidence=0.9)),  # correct
            ("p2", _diag(DiagnosisLabel.ARITHMETIC_ERROR, confidence=0.8)),  # incorrect
            ("p3", _diag(DiagnosisLabel.UNKNOWN_ERROR, confidence=0.2)),     # incorrect
        ]
        gt = {
            "p1": DiagnosisLabel.ARITHMETIC_ERROR,
            "p2": DiagnosisLabel.QUANTITY_RELATION_ERROR,
            "p3": DiagnosisLabel.TARGET_MISUNDERSTANDING,
        }
        report = compute_confidence_calibration(predictions, gt, num_bins=5)
        assert report.labeled_count == 3
        assert report.ece >= 0
        assert report.mce >= 0
        assert len(report.bins) == 5

    def test_calibration_invalid_bins(self):
        with pytest.raises(ValueError):
            compute_confidence_calibration([], {}, num_bins=0)


class TestSymbolicAblation:
    def test_ablation_delta(self):
        with_sym = [
            ("p1", _diag(DiagnosisLabel.ARITHMETIC_ERROR, 0.8)),
            ("p2", _diag(DiagnosisLabel.QUANTITY_RELATION_ERROR, 0.9)),
        ]
        without_sym = [
            ("p1", _diag(DiagnosisLabel.UNKNOWN_ERROR, 0.7)),
            ("p2", _diag(DiagnosisLabel.QUANTITY_RELATION_ERROR, 0.6)),
        ]
        gt = {
            "p1": DiagnosisLabel.ARITHMETIC_ERROR,
            "p2": DiagnosisLabel.QUANTITY_RELATION_ERROR,
        }
        report = compare_symbolic_ablation(with_sym, without_sym, gt)
        assert report.labeled_count == 2
        assert report.with_symbolic_correct == 2
        assert report.without_symbolic_correct == 1
        assert report.delta_accuracy > 0
        assert report.changed_predictions == 1
        assert report.improved_cases == 1


class TestExportAuditLog:
    def test_export_format(self):
        predictions = [("p1", _diag(DiagnosisLabel.ARITHMETIC_ERROR))]
        ground_truth = {"p1": DiagnosisLabel.ARITHMETIC_ERROR}
        report = evaluate_diagnoses(predictions, ground_truth)

        log = export_audit_log(report)
        assert len(log) == 1
        assert log[0]["problem_id"] == "p1"
        assert log[0]["predicted"] == "arithmetic_error"
        assert log[0]["expected"] == "arithmetic_error"
        assert log[0]["match"] is True

    def test_export_without_ground_truth(self):
        predictions = [("p1", _diag(DiagnosisLabel.UNKNOWN_ERROR))]
        report = evaluate_diagnoses(predictions)
        log = export_audit_log(report)
        assert log[0]["expected"] is None
        assert log[0]["match"] is False
