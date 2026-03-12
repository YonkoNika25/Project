import pytest
from src.models import (
    AnswerCheckResult, Correctness, DiagnosisLabel,
    ErrorLocalization, DiagnosisResult,
    VerificationResult, VerificationStatus,
)
from src.diagnosis.engine import (
    diagnose,
    diagnose_with_rules,
    parse_diagnosis_response,
    build_diagnosis_prompt,
    diagnose_with_symbolic_evidence,
)


def _check(correctness: Correctness, student_val=None) -> AnswerCheckResult:
    return AnswerCheckResult(
        correctness=correctness,
        comparison_type="exact",
        student_value=student_val,
        normalization_status="success" if student_val is not None else "failed",
        reference_value=8.0,
    )


class TestDiagnoseWithRules:
    def test_correct_answer(self):
        result = diagnose_with_rules(_check(Correctness.CORRECT, 8.0))
        assert result.label == DiagnosisLabel.CORRECT_ANSWER
        assert result.confidence == 1.0

    def test_unparseable(self):
        result = diagnose_with_rules(_check(Correctness.UNPARSEABLE))
        assert result.label == DiagnosisLabel.UNPARSEABLE_ANSWER

    def test_incorrect_returns_none(self):
        result = diagnose_with_rules(_check(Correctness.INCORRECT, 10.0))
        assert result is None


class TestParseDiagnosisResponse:
    def test_valid_json(self):
        raw = '{"label": "arithmetic_error", "localization": "final_computation", "explanation": "wrong calc"}'
        result = parse_diagnosis_response(raw)
        assert result.label == DiagnosisLabel.ARITHMETIC_ERROR
        assert result.localization == ErrorLocalization.FINAL_COMPUTATION

    def test_json_in_text(self):
        raw = 'Here is my analysis:\n{"label": "quantity_relation_error", "localization": "intermediate_step", "explanation": "bad setup"}\nDone.'
        result = parse_diagnosis_response(raw)
        assert result.label == DiagnosisLabel.QUANTITY_RELATION_ERROR

    def test_invalid_label_fallback(self):
        raw = '{"label": "made_up_error", "localization": "final_computation", "explanation": "test"}'
        result = parse_diagnosis_response(raw)
        assert result.label == DiagnosisLabel.UNKNOWN_ERROR

    def test_no_json_fallback(self):
        raw = "I think the student made an arithmetic error"
        result = parse_diagnosis_response(raw)
        assert result.label == DiagnosisLabel.UNKNOWN_ERROR
        assert result.fallback_used is True

    def test_malformed_json_fallback(self):
        raw = '{"label": "arithmetic_error", broken}'
        result = parse_diagnosis_response(raw)
        assert result.fallback_used is True


class TestDiagnose:
    def test_correct_no_llm_needed(self):
        check = _check(Correctness.CORRECT, 8.0)
        result = diagnose("Problem?", "Solution", 8.0, "8", check)
        assert result.label == DiagnosisLabel.CORRECT_ANSWER

    def test_unparseable_no_llm_needed(self):
        check = _check(Correctness.UNPARSEABLE)
        result = diagnose("Problem?", "Solution", 8.0, "??", check)
        assert result.label == DiagnosisLabel.UNPARSEABLE_ANSWER

    def test_incorrect_no_llm_fallback(self):
        check = _check(Correctness.INCORRECT, 10.0)
        result = diagnose("Problem?", "Solution", 8.0, "10", check, llm_callable=None)
        assert result.label == DiagnosisLabel.UNKNOWN_ERROR
        assert result.fallback_used is True

    def test_incorrect_with_llm(self):
        def mock_llm(prompt):
            return '{"label": "arithmetic_error", "localization": "final_computation", "explanation": "Student added wrong"}'

        check = _check(Correctness.INCORRECT, 10.0)
        result = diagnose("5+3=?", "5+3=8", 8.0, "10", check, llm_callable=mock_llm)
        assert result.label == DiagnosisLabel.ARITHMETIC_ERROR

    def test_llm_exception_fallback(self):
        def broken_llm(prompt):
            raise RuntimeError("API down")

        check = _check(Correctness.INCORRECT, 10.0)
        result = diagnose("Problem?", "Solution", 8.0, "10", check, llm_callable=broken_llm)
        assert result.label == DiagnosisLabel.UNKNOWN_ERROR
        assert result.fallback_used is True

    def test_prompt_contains_context(self):
        check = _check(Correctness.INCORRECT, 10.0)
        prompt = build_diagnosis_prompt("What is 5+3?", "5+3=8", 8.0, "10", check)
        assert "What is 5+3?" in prompt
        assert "5+3=8" in prompt
        assert "10" in prompt


class TestDiagnoseWithSymbolicEvidence:
    def test_conflict_maps_to_quantity_relation_error(self):
        check = _check(Correctness.INCORRECT, 6.0)
        vr = VerificationResult(
            status=VerificationStatus.CONFLICT,
            predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
            localization_hint=ErrorLocalization.INTERMEDIATE_STEP,
            confidence=0.92,
            explanation="conflict",
        )
        result = diagnose_with_symbolic_evidence(check, vr)
        assert result is not None
        assert result.label == DiagnosisLabel.QUANTITY_RELATION_ERROR

    def test_verified_maps_to_arithmetic_error(self):
        check = _check(Correctness.INCORRECT, 15.0)
        vr = VerificationResult(
            status=VerificationStatus.VERIFIED,
            confidence=0.7,
            explanation="consistent",
        )
        result = diagnose_with_symbolic_evidence(check, vr)
        assert result is not None
        assert result.label == DiagnosisLabel.ARITHMETIC_ERROR


class TestPromptWithSymbolicEvidence:
    def test_prompt_contains_symbolic_section(self):
        check = _check(Correctness.INCORRECT, 10.0)
        vr = VerificationResult(
            status=VerificationStatus.CONFLICT,
            predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
            localization_hint=ErrorLocalization.INTERMEDIATE_STEP,
            confidence=0.9,
            evidence_flags=["flag_a"],
            explanation="x",
        )
        prompt = build_diagnosis_prompt(
            "What is 5+3?",
            "5+3=8",
            8.0,
            "10",
            check,
            verification_result=vr,
        )
        assert "Symbolic Evidence" in prompt
        assert "status=conflict" in prompt
