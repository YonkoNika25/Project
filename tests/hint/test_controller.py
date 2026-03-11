import pytest
from src.models import (
    HintLevel, HintResult, DiagnosisLabel, DiagnosisResult, ErrorLocalization
)
from src.hint.controller import HintController


def _diag(label: DiagnosisLabel) -> DiagnosisResult:
    return DiagnosisResult(
        label=label,
        localization=ErrorLocalization.FINAL_COMPUTATION,
        explanation="test explanation",
        confidence=0.9
    )


class TestHintController:
    def test_correct_answer_fast_path(self):
        controller = HintController()
        diag = _diag(DiagnosisLabel.CORRECT_ANSWER)
        result = controller.get_hint("P", "S", 10.0, "10", diag)
        
        assert "chính xác" in result.hint_text
        assert result.fallback_used is False
        assert result.generated_status == "success"

    def test_successful_generation(self):
        def mock_llm(prompt):
            return '{"hint_text": "Hãy kiểm tra lại phép tính cộng."}'
            
        controller = HintController(llm_callable=mock_llm)
        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = controller.get_hint("5+5", "10", 10.0, "11", diag)
        
        assert result.hint_text == "Hãy kiểm tra lại phép tính cộng."
        assert result.fallback_used is False
        assert result.generated_status == "success"

    def test_spoiler_triggers_fallback(self):
        def mock_llm_spoiler(prompt):
            return '{"hint_text": "Đáp án là 10 nhé."}'  # Spoiler!
            
        controller = HintController(llm_callable=mock_llm_spoiler, max_retries=0)
        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        # reference_answer is 10.0
        result = controller.get_hint("5+5", "10", 10.0, "11", diag)
        
        assert result.fallback_used is True
        # Check if it returns the Vietnamese fallback for arithmetic error
        assert "tính toán" in result.hint_text

    def test_llm_failure_triggers_fallback(self):
        def broken_llm(prompt):
            raise RuntimeError("API Down")
            
        controller = HintController(llm_callable=broken_llm, max_retries=0)
        diag = _diag(DiagnosisLabel.TARGET_MISUNDERSTANDING)
        result = controller.get_hint("P", "S", 10.0, "W", diag)
        
        assert result.fallback_used is True
        assert "câu hỏi" in result.hint_text

    def test_retry_then_success(self):
        call_count = 0
        def retry_mock(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '{"hint_text": "Đáp án là 10."}' # Spoiler
            return '{"hint_text": "Hãy thử cộng lại."}' # Good
            
        controller = HintController(llm_callable=retry_mock, max_retries=1)
        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = controller.get_hint("5+5", "10", 10.0, "11", diag)
        
        assert result.hint_text == "Hãy thử cộng lại."
        assert result.fallback_used is False
        assert call_count == 2
