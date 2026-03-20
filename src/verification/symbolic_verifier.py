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


def _find_matching_quantity(student: float, values: list[float]) -> float | None:
    for value in values:
        if _approx_equal(student, value):
            return value
    return None


def _relation_error_candidates(
    values: list[float],
    expected_operation: OperationType,
) -> list[tuple[float, str]]:
    candidates: list[tuple[float, str]] = []

    if len(values) >= 2:
        candidates.append((values[0] - values[1], "first_subtraction_only"))
        candidates.append((values[0] + values[1], "partial_sum_first_two"))
        candidates.append((abs(values[0] - values[1]), "difference_of_first_two"))

    if len(values) >= 3:
        for end in range(2, len(values)):
            candidates.append((sum(values[:end]), f"partial_sum_first_{end}"))
        candidates.append((sum(values[1:]), "drop_initial_quantity"))
        candidates.append((abs(max(values) - min(values)), "comparison_extremes"))

    if expected_operation == OperationType.ADDITIVE:
        candidates.append((abs(max(values) - min(values)), "comparison_instead_of_total"))
    elif expected_operation == OperationType.SUBTRACTIVE:
        candidates.append((sum(values), "sum_instead_of_difference"))

    seen: set[float] = set()
    deduped: list[tuple[float, str]] = []
    for candidate, reason in candidates:
        rounded = round(candidate, 9)
        if rounded in seen:
            continue
        seen.add(rounded)
        deduped.append((candidate, reason))
    return deduped


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

    matching_quantity = _find_matching_quantity(student, values)
    if matching_quantity is not None and not _approx_equal(student, reference):
        return VerificationResult(
            status=VerificationStatus.CONFLICT,
            localization_hint=ErrorLocalization.TARGET_SELECTION,
            predicted_label=DiagnosisLabel.TARGET_MISUNDERSTANDING,
            confidence=0.82,
            evidence_flags=["student_matches_problem_quantity"],
            explanation="Student answer matches a visible quantity in the problem instead of the requested target.",
        )

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

    for candidate, reason in _relation_error_candidates(values, state.expected_operation):
        if _approx_equal(student, candidate) and not _approx_equal(reference, candidate):
            return VerificationResult(
                status=VerificationStatus.CONFLICT,
                localization_hint=ErrorLocalization.COMBINING_QUANTITIES,
                predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
                confidence=0.84,
                evidence_flags=[reason, "student_matches_intermediate_combination"],
                explanation="Student answer matches an intermediate quantity-combination strategy instead of the final target relation.",
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
