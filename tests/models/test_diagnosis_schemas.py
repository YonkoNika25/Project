import pytest
from pydantic import ValidationError
from src.models import DiagnosisLabel, ErrorLocalization, DiagnosisResult


class TestDiagnosisLabel:
    def test_all_labels_exist(self):
        expected = {"correct_answer", "arithmetic_error", "quantity_relation_error",
                    "target_misunderstanding", "unparseable_answer", "unknown_error"}
        actual = {l.value for l in DiagnosisLabel}
        assert actual == expected


class TestDiagnosisResult:
    def test_valid(self):
        result = DiagnosisResult(
            label=DiagnosisLabel.ARITHMETIC_ERROR,
            localization=ErrorLocalization.FINAL_COMPUTATION,
            explanation="Student made calculation error in last step",
            confidence=0.9,
        )
        assert result.label == DiagnosisLabel.ARITHMETIC_ERROR
        assert result.fallback_used is False

    def test_correct_answer(self):
        result = DiagnosisResult(
            label=DiagnosisLabel.CORRECT_ANSWER,
            localization=ErrorLocalization.NONE,
            explanation="Student answered correctly",
            confidence=1.0,
        )
        assert result.label == DiagnosisLabel.CORRECT_ANSWER

    def test_fallback(self):
        result = DiagnosisResult(
            label=DiagnosisLabel.UNKNOWN_ERROR,
            localization=ErrorLocalization.UNKNOWN,
            explanation="Could not determine error type",
            confidence=0.3,
            fallback_used=True,
        )
        assert result.fallback_used is True

    def test_invalid_confidence(self):
        with pytest.raises(ValidationError):
            DiagnosisResult(
                label=DiagnosisLabel.ARITHMETIC_ERROR,
                localization=ErrorLocalization.FINAL_COMPUTATION,
                explanation="Test",
                confidence=1.5,
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            DiagnosisResult(
                label=DiagnosisLabel.ARITHMETIC_ERROR,
                localization=ErrorLocalization.FINAL_COMPUTATION,
                explanation="Test",
                confidence=0.8,
                extra="nope",
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            DiagnosisResult(label=DiagnosisLabel.ARITHMETIC_ERROR)
