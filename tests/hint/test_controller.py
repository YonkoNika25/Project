import pytest
from src.models import (
    HintLevel,
    DiagnosisLabel,
    DiagnosisResult,
    ErrorLocalization,
    VerificationResult,
    VerificationStatus,
)
from src.hint.controller import HintController


def _diag(label: DiagnosisLabel, confidence: float = 0.9) -> DiagnosisResult:
    return DiagnosisResult(
        label=label,
        localization=ErrorLocalization.FINAL_COMPUTATION,
        explanation="test explanation",
        confidence=confidence,
    )


class TestHintController:
    def test_correct_answer_fast_path(self):
        controller = HintController()
        diag = _diag(DiagnosisLabel.CORRECT_ANSWER)
        result = controller.get_hint("P", "S", 10.0, "10", diag)

        assert "correct" in result.hint_text.lower()
        assert result.fallback_used is False
        assert result.generated_status == "success"

    def test_successful_generation(self):
        def mock_llm(prompt):
            return '{"hint_text": "Try checking the addition calculation in the next step."}'

        controller = HintController(llm_callable=mock_llm)
        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = controller.get_hint("5+5", "10", 10.0, "11", diag)

        assert "calculation" in result.hint_text
        assert result.fallback_used is False
        assert result.generated_status == "success"

    def test_spoiler_triggers_fallback(self):
        def mock_llm_spoiler(prompt):
            return '{"hint_text": "The answer is 10."}'

        controller = HintController(llm_callable=mock_llm_spoiler, max_retries=0)
        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = controller.get_hint("5+5", "10", 10.0, "11", diag)

        assert result.fallback_used is True
        assert "calculation" in result.hint_text.lower()

    def test_alignment_failure_triggers_fallback(self):
        def mock_llm_misaligned(prompt):
            return '{"hint_text": "Read the question again to see what is being asked.", "hint_level": "next_step"}'

        controller = HintController(llm_callable=mock_llm_misaligned, max_retries=0)
        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = controller.get_hint("5+5", "10", 10.0, "11", diag)

        assert result.fallback_used is True

    def test_llm_failure_triggers_fallback(self):
        def broken_llm(prompt):
            raise RuntimeError("API Down")

        controller = HintController(llm_callable=broken_llm, max_retries=0)
        diag = _diag(DiagnosisLabel.TARGET_MISUNDERSTANDING)
        result = controller.get_hint("P", "S", 10.0, "W", diag)

        assert result.fallback_used is True
        assert "question" in result.hint_text.lower()

    def test_retry_then_success(self):
        call_count = 0

        def retry_mock(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '{"hint_text": "The answer is 10."}'
            return '{"hint_text": "Try adding again in the next step."}'

        controller = HintController(llm_callable=retry_mock, max_retries=1)
        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = controller.get_hint("5+5", "10", 10.0, "11", diag)

        assert "adding again" in result.hint_text.lower()
        assert result.fallback_used is False
        assert call_count == 2

    def test_conflict_verification_prefers_relational_level(self):
        prompts = []

        def mock_llm(prompt):
            prompts.append(prompt)
            return '{"hint_text": "Check the relationship between quantities before choosing add or subtract.", "hint_level": "relational"}'

        controller = HintController(llm_callable=mock_llm, max_retries=0)
        diag = _diag(DiagnosisLabel.QUANTITY_RELATION_ERROR)
        vr = VerificationResult(
            status=VerificationStatus.CONFLICT,
            predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
            confidence=0.9,
        )
        result = controller.get_hint("P", "S", 10.0, "6", diag, verification_result=vr)

        assert result.fallback_used is False
        assert result.hint_level == HintLevel.RELATIONAL
