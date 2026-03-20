import pytest
from src.models import (
    HintLevel, HintResult, DiagnosisLabel, DiagnosisResult, ErrorLocalization
)
from src.hint.engine import (
    generate_hint,
    parse_hint_response,
    build_hint_prompt,
)


def _diag(label: DiagnosisLabel) -> DiagnosisResult:
    return DiagnosisResult(
        label=label,
        localization=ErrorLocalization.FINAL_COMPUTATION,
        explanation="test explanation",
        confidence=0.9
    )


class TestParseHintResponse:
    def test_valid_json(self):
        raw = '{"hint_level": "conceptual", "hint_text": "Look at the units."}'
        result = parse_hint_response(raw, DiagnosisLabel.ARITHMETIC_ERROR, HintLevel.NEXT_STEP)
        assert result.hint_level == HintLevel.CONCEPTUAL
        assert result.hint_text == "Look at the units."
        assert result.generated_status == "success"

    def test_json_in_text(self):
        raw = 'Here is the hint:\n{"hint_text": "Check your addition."}\nHope this helps!'
        result = parse_hint_response(raw, DiagnosisLabel.ARITHMETIC_ERROR, HintLevel.NEXT_STEP)
        assert result.hint_level == HintLevel.NEXT_STEP  # Used requested because response was missing it
        assert result.hint_text == "Check your addition."

    def test_failure_fallback(self):
        raw = "Not a JSON"
        result = parse_hint_response(raw, DiagnosisLabel.ARITHMETIC_ERROR, HintLevel.NEXT_STEP)
        assert result.generated_status == "failure"
        assert result.fallback_used is True


class TestGenerateHint:
    def test_correct_answer_no_llm(self):
        # Policy for CORRECT_ANSWER is an empty list of levels
        diag = _diag(DiagnosisLabel.CORRECT_ANSWER)
        result = generate_hint("Problem", "Sol", "10", diag)
        assert "correct" in result.hint_text.lower()
        assert result.generated_status == "success"

    def test_incorrect_no_llm_callable(self):
        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = generate_hint("Problem", "Sol", "12", diag, llm_callable=None)
        assert result.generated_status == "failure"
        assert result.fallback_used is True

    def test_successful_llm_generation(self):
        def mock_llm(prompt):
            return '{"hint_text": "Try recalculating the last step."}'

        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = generate_hint(
            "5+5",
            "10",
            "11",
            diag,
            llm_callable=mock_llm,
            preferred_level=HintLevel.NEXT_STEP,
        )
        assert result.hint_text == "Try recalculating the last step."
        assert result.hint_level == HintLevel.NEXT_STEP
        assert result.generated_status == "success"

    def test_llm_exception_handling(self):
        def broken_llm(prompt):
            raise RuntimeError("LLM is broken")

        diag = _diag(DiagnosisLabel.ARITHMETIC_ERROR)
        result = generate_hint("P", "S", "A", diag, llm_callable=broken_llm)
        assert result.generated_status == "failure"
        assert result.fallback_used is True

    def test_prompt_content(self):
        diag = _diag(DiagnosisLabel.TARGET_MISUNDERSTANDING)
        prompt = build_hint_prompt("Solve for X", "X is 5", "X is 10", diag, HintLevel.CONCEPTUAL)
        assert "Solve for X" in prompt
        assert "X is 5" in prompt
        assert "X is 10" in prompt
        assert "target_misunderstanding" in prompt
        assert "conceptual" in prompt
