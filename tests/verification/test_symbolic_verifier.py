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


def test_target_misunderstanding_when_student_matches_visible_problem_quantity():
    state = SymbolicState(
        quantities=[
            QuantityFact(surface_form="5", value=5),
            QuantityFact(surface_form="3", value=3),
            QuantityFact(surface_form="20", value=20),
        ],
        target_text="If there are a total of 20 gnomes on the street, how many gnomes does the fifth house have?",
        expected_operation=OperationType.ADDITIVE,
        builder_confidence=0.8,
    )
    result = verify_symbolic_consistency(state, _check(student=5.0, reference=8.0))
    assert result.status == VerificationStatus.CONFLICT
    assert result.predicted_label == DiagnosisLabel.TARGET_MISUNDERSTANDING
    assert result.localization_hint == ErrorLocalization.TARGET_SELECTION


def test_quantity_relation_error_when_student_matches_intermediate_combination():
    state = SymbolicState(
        quantities=[
            QuantityFact(surface_form="290", value=290),
            QuantityFact(surface_form="24", value=24),
            QuantityFact(surface_form="10", value=10),
            QuantityFact(surface_form="8", value=8),
        ],
        target_text="If 10 of the cans are holding 8 liters each, how much oil is each of the remaining cans holding?",
        expected_operation=OperationType.SUBTRACTIVE,
        builder_confidence=0.8,
    )
    result = verify_symbolic_consistency(state, _check(student=266.0, reference=15.0))
    assert result.status == VerificationStatus.CONFLICT
    assert result.predicted_label == DiagnosisLabel.QUANTITY_RELATION_ERROR
    assert result.localization_hint == ErrorLocalization.COMBINING_QUANTITIES
