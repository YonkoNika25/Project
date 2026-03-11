"""End-to-end hint controller: orchestrates generation, verification, and fallback."""
import logging
from typing import Optional

from src.models import (
    HintResult,
    HintLevel,
    DiagnosisResult,
    DiagnosisLabel,
)
from src.hint.engine import generate_hint
from src.hint.verifier import verify_hint_no_spoiler
from src.hint.fallback import get_static_fallback_hint

logger = logging.getLogger(__name__)

class HintController:
    """Orchestrator for pedagogical hint generation."""

    def __init__(self, llm_callable=None, max_retries: int = 1):
        self.llm_callable = llm_callable
        self.max_retries = max_retries

    def get_hint(
        self,
        problem_text: str,
        reference_solution_text: str,
        reference_answer: float,
        student_raw: str,
        diagnosis: DiagnosisResult,
        preferred_level: Optional[HintLevel] = None,
    ) -> HintResult:
        """Get a verified pedagogical hint.
        
        Lifecycle:
        1. Fast-path for correct answers.
        2. Generate hint via engine.
        3. Verify hint (no spoilers).
        4. Retry if spoiler detected (up to max_retries).
        5. Fallback to static hint if all else fails.
        """
        # 1. Correct answer fast-path
        if diagnosis.label == DiagnosisLabel.CORRECT_ANSWER:
            return HintResult(
                hint_level=HintLevel.CONCEPTUAL,
                hint_text="Đáp án của em hoàn toàn chính xác! Làm tốt lắm.",
                generated_status="success",
                diagnosis_label_used=diagnosis.label,
                fallback_used=False,
            )

        # 2. & 3. Generation and Verification loop
        last_failed_hint = None
        for attempt in range(self.max_retries + 1):
            hint_res = generate_hint(
                problem_text=problem_text,
                reference_solution_text=reference_solution_text,
                student_raw=student_raw,
                diagnosis=diagnosis,
                llm_callable=self.llm_callable,
                preferred_level=preferred_level,
            )

            if hint_res.generated_status == "success":
                # Check for spoilers
                if verify_hint_no_spoiler(hint_res.hint_text, reference_answer):
                    return hint_res
                else:
                    logger.warning("Attempt %d: Spoiler detected in generated hint.", attempt + 1)
                    last_failed_hint = hint_res
            else:
                logger.warning("Attempt %d: Hint generation failed.", attempt + 1)
                last_failed_hint = hint_res

        # 4. Fallback if no clean hint generated
        logger.info("Falling back to static hint for label: %s", diagnosis.label)
        static_text = get_static_fallback_hint(diagnosis.label)
        
        return HintResult(
            hint_level=last_failed_hint.hint_level if last_failed_hint else HintLevel.CONCEPTUAL,
            hint_text=static_text,
            generated_status="success",
            diagnosis_label_used=diagnosis.label,
            fallback_used=True,
        )
