"""Answer checker: compares normalized student answer against reference solution."""
import logging

from src.models import AnswerCheckResult, Correctness
from src.checker.student_normalizer import normalize_student_answer

logger = logging.getLogger(__name__)


def check_answer(
    student_raw: str,
    reference_value: float,
) -> AnswerCheckResult:
    """Check a student's answer against the reference answer.

    Args:
        student_raw: Raw student answer text.
        reference_value: The correct numeric answer from the reference solution.

    Returns:
        AnswerCheckResult with correctness status.
    """
    student_value, parsed_ok = normalize_student_answer(student_raw)

    if not parsed_ok or student_value is None:
        return AnswerCheckResult(
            correctness=Correctness.UNPARSEABLE,
            comparison_type="none",
            student_value=None,
            normalization_status="failed",
            reference_value=reference_value,
        )

    # Exact float match (GSM8K answers are integers, so this is sufficient)
    if student_value == reference_value:
        return AnswerCheckResult(
            correctness=Correctness.CORRECT,
            comparison_type="exact",
            student_value=student_value,
            normalization_status="success",
            reference_value=reference_value,
        )

    # Numeric-equivalent check (within floating point tolerance)
    if abs(student_value - reference_value) < 1e-6:
        return AnswerCheckResult(
            correctness=Correctness.CORRECT,
            comparison_type="numeric_equivalent",
            student_value=student_value,
            normalization_status="success",
            reference_value=reference_value,
        )

    return AnswerCheckResult(
        correctness=Correctness.INCORRECT,
        comparison_type="exact",
        student_value=student_value,
        normalization_status="success",
        reference_value=reference_value,
    )
