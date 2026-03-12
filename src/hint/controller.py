"""End-to-end hint controller: orchestrates generation, verification, and fallback."""
import logging
from typing import Optional

from src.models import (
    HintResult,
    HintLevel,
    DiagnosisResult,
    DiagnosisLabel,
    VerificationResult,
    VerificationStatus,
)
from src.hint.engine import generate_hint
from src.hint.verifier import verify_hint_no_spoiler, verify_hint_alignment
from src.hint.fallback import get_static_fallback_hint

logger = logging.getLogger(__name__)


class HintController:
    """Orchestrator for pedagogical hint generation."""

    def __init__(self, llm_callable=None, max_retries: int = 1):
        self.llm_callable = llm_callable
        self.max_retries = max_retries

    @staticmethod
    def _derive_preferred_level(
        diagnosis: DiagnosisResult,
        verification_result: Optional[VerificationResult],
        preferred_level: Optional[HintLevel],
    ) -> Optional[HintLevel]:
        if preferred_level is not None:
            return preferred_level

        if verification_result is not None:
            if verification_result.status == VerificationStatus.CONFLICT:
                return HintLevel.RELATIONAL
            if verification_result.status == VerificationStatus.INSUFFICIENT_EVIDENCE:
                return HintLevel.CONCEPTUAL

        if diagnosis.confidence < 0.5:
            return HintLevel.CONCEPTUAL

        if diagnosis.label == DiagnosisLabel.ARITHMETIC_ERROR:
            return HintLevel.NEXT_STEP
        if diagnosis.label == DiagnosisLabel.QUANTITY_RELATION_ERROR:
            return HintLevel.RELATIONAL

        return None

    def get_hint(
        self,
        problem_text: str,
        reference_solution_text: str,
        reference_answer: float,
        student_raw: str,
        diagnosis: DiagnosisResult,
        preferred_level: Optional[HintLevel] = None,
        verification_result: Optional[VerificationResult] = None,
    ) -> HintResult:
        """Get a verified pedagogical hint.

        Lifecycle:
        1. Fast-path for correct answers.
        2. Generate hint via engine.
        3. Verify hint (no spoilers + pedagogical alignment).
        4. Retry if checks fail (up to max_retries).
        5. Fallback to static hint if all else fails.
        """
        if diagnosis.label == DiagnosisLabel.CORRECT_ANSWER:
            return HintResult(
                hint_level=HintLevel.CONCEPTUAL,
                hint_text="Đáp án của em hoàn toàn chính xác! Làm tốt lắm.",
                generated_status="success",
                diagnosis_label_used=diagnosis.label,
                fallback_used=False,
            )

        derived_level = self._derive_preferred_level(
            diagnosis=diagnosis,
            verification_result=verification_result,
            preferred_level=preferred_level,
        )

        last_failed_hint = None
        for attempt in range(self.max_retries + 1):
            hint_res = generate_hint(
                problem_text=problem_text,
                reference_solution_text=reference_solution_text,
                student_raw=student_raw,
                diagnosis=diagnosis,
                llm_callable=self.llm_callable,
                preferred_level=derived_level,
            )

            if hint_res.generated_status == "success":
                spoiler_ok = verify_hint_no_spoiler(hint_res.hint_text, reference_answer)
                alignment_ok = verify_hint_alignment(
                    hint_res.hint_text,
                    diagnosis_label=diagnosis.label,
                    expected_level=hint_res.hint_level,
                )

                if spoiler_ok and alignment_ok:
                    return hint_res

                if not spoiler_ok:
                    logger.warning("Attempt %d: Spoiler detected in generated hint.", attempt + 1)
                if not alignment_ok:
                    logger.warning("Attempt %d: Hint pedagogical alignment check failed.", attempt + 1)
                last_failed_hint = hint_res
            else:
                logger.warning("Attempt %d: Hint generation failed.", attempt + 1)
                last_failed_hint = hint_res

        logger.info("Falling back to static hint for label: %s", diagnosis.label)
        static_text = get_static_fallback_hint(diagnosis.label)

        fallback_level = derived_level or HintLevel.CONCEPTUAL
        if last_failed_hint is not None:
            fallback_level = last_failed_hint.hint_level

        return HintResult(
            hint_level=fallback_level,
            hint_text=static_text,
            generated_status="success",
            diagnosis_label_used=diagnosis.label,
            fallback_used=True,
        )
