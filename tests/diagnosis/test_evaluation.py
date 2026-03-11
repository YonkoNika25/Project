import pytest
from src.models import DiagnosisLabel, DiagnosisResult, ErrorLocalization
from src.diagnosis.evaluation import evaluate_diagnoses, export_audit_log


def _diag(label: DiagnosisLabel) -> DiagnosisResult:
    return DiagnosisResult(
        label=label,
        localization=ErrorLocalization.UNKNOWN,
        explanation="test",
        confidence=0.8,
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
            ("p2", _diag(DiagnosisLabel.UNKNOWN_ERROR)),  # wrong
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
