from src.models import (
    AnswerCheckResult,
    Correctness,
    DiagnosisLabel,
    ErrorLocalization,
    OperationType,
    QuantityFact,
    SymbolicState,
    VerificationStatus,
)
from src.verification.symbolic_verifier import verify_symbolic_consistency


def _check(student, reference):
    return AnswerCheckResult(
        correctness=Correctness.INCORRECT,
        comparison_type="numeric_equivalent",
        student_value=student,
        normalization_status="success",
        reference_value=reference,
    )


def test_conflict_when_expected_additive_but_student_subtractive():
    state = SymbolicState(
        quantities=[QuantityFact(surface_form="10", value=10), QuantityFact(surface_form="4", value=4)],
        expected_operation=OperationType.ADDITIVE,
        builder_confidence=0.8,
    )
    result = verify_symbolic_consistency(state, _check(student=6.0, reference=14.0))
    assert result.status == VerificationStatus.CONFLICT
    assert result.predicted_label == DiagnosisLabel.QUANTITY_RELATION_ERROR
    assert result.localization_hint == ErrorLocalization.INTERMEDIATE_STEP


def test_verified_when_both_follow_same_hypothesis():
    state = SymbolicState(
        quantities=[QuantityFact(surface_form="10", value=10), QuantityFact(surface_form="4", value=4)],
        expected_operation=OperationType.ADDITIVE,
        builder_confidence=0.8,
    )
    result = verify_symbolic_consistency(state, _check(student=15.0, reference=14.0))
    assert result.status == VerificationStatus.VERIFIED
    assert result.predicted_label == DiagnosisLabel.ARITHMETIC_ERROR
