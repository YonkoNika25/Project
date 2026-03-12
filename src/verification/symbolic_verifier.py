"""Verify student/reference consistency against symbolic hypotheses."""
from src.models import (
    AnswerCheckResult,
    Correctness,
    DiagnosisLabel,
    ErrorLocalization,
    OperationType,
    SymbolicState,
    VerificationResult,
    VerificationStatus,
)


def _approx_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def verify_symbolic_consistency(
    state: SymbolicState,
    check_result: AnswerCheckResult,
) -> VerificationResult:
    """Return structured evidence to support grounded diagnosis decisions."""
    if check_result.correctness == Correctness.UNPARSEABLE or check_result.student_value is None:
        return VerificationResult(
            status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            localization_hint=ErrorLocalization.UNKNOWN,
            confidence=0.2,
            evidence_flags=["student_unparseable"],
            explanation="Student value unavailable for symbolic verification.",
        )

    values = [q.value for q in state.quantities]
    if len(values) < 2:
        return VerificationResult(
            status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            localization_hint=ErrorLocalization.UNKNOWN,
            confidence=0.2,
            evidence_flags=["insufficient_quantities"],
            explanation="Need at least two quantities to test operation hypotheses.",
        )

    additive = sum(values)
    subtractive = values[0] - sum(values[1:])
    student = check_result.student_value
    reference = check_result.reference_value

    student_matches_add = _approx_equal(student, additive)
    student_matches_sub = _approx_equal(student, subtractive)
    ref_matches_add = _approx_equal(reference, additive)
    ref_matches_sub = _approx_equal(reference, subtractive)

    if state.expected_operation == OperationType.ADDITIVE and student_matches_sub and ref_matches_add:
        return VerificationResult(
            status=VerificationStatus.CONFLICT,
            localization_hint=ErrorLocalization.INTERMEDIATE_STEP,
            predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
            confidence=0.9,
            evidence_flags=["student_matches_subtractive_interpretation", "expected_additive_relation"],
            explanation="Student answer matches subtractive interpretation while additive relation is expected.",
        )

    if state.expected_operation == OperationType.SUBTRACTIVE and student_matches_add and ref_matches_sub:
        return VerificationResult(
            status=VerificationStatus.CONFLICT,
            localization_hint=ErrorLocalization.INTERMEDIATE_STEP,
            predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
            confidence=0.9,
            evidence_flags=["student_matches_additive_interpretation", "expected_subtractive_relation"],
            explanation="Student answer matches additive interpretation while subtractive relation is expected.",
        )

    student_prefers_add = abs(student - additive) <= abs(student - subtractive)
    reference_prefers_add = abs(reference - additive) <= abs(reference - subtractive)

    if student_prefers_add == reference_prefers_add:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            localization_hint=ErrorLocalization.FINAL_COMPUTATION,
            predicted_label=DiagnosisLabel.ARITHMETIC_ERROR,
            confidence=0.65,
            evidence_flags=["operation_hypothesis_consistent"],
            explanation="Student/reference align on the same operation hypothesis; likely arithmetic slip.",
        )

    return VerificationResult(
        status=VerificationStatus.INSUFFICIENT_EVIDENCE,
        localization_hint=ErrorLocalization.UNKNOWN,
        confidence=0.35,
        evidence_flags=["no_interpretation_match"],
        explanation="Could not map student/reference values to operation hypotheses with confidence.",
    )
