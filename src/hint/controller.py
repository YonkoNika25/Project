"""Hint controller that generates and verifies hint output."""
from __future__ import annotations

from src.hint.generator import generate_hint_text
from src.hint.repair import repair_hint_text
from src.hint.verifier import verify_hint_text
from src.llm import LLMClient
from src.models import (
    CanonicalReference,
    DiagnosisResult,
    FormalizedProblem,
    HintMode,
    HintPlan,
    HintResult,
    HintStrategy,
    TeacherMove,
)


def _fallback_hint(plan: HintPlan) -> str:
    if plan.teacher_move == TeacherMove.REFOCUS_TARGET:
        return "Read the question again and decide what quantity you still need to find."
    if plan.teacher_move == TeacherMove.CHECK_RELATIONSHIP:
        return "Think about how the quantities should be related before you calculate."
    if plan.teacher_move == TeacherMove.RECOMPUTE_STEP:
        return "Check that arithmetic step carefully and try it again."
    if plan.teacher_move == TeacherMove.CONTINUE_FROM_STEP:
        return "Use the quantities you already found and recompute the last step carefully."
    if plan.teacher_move == TeacherMove.METACOGNITIVE_PROMPT:
        return "Restate what the problem is asking for and give one clear numeric answer."
    return "Your answer is correct."


def build_hint_result(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    plan: HintPlan,
    strategy: HintStrategy | None = None,
    hint_mode: HintMode = HintMode.NORMAL,
    llm_client: LLMClient | None = None,
) -> HintResult:
    """Generate a hint and verify it against the hint plan."""
    hint_text = generate_hint_text(
        problem,
        reference,
        plan,
        strategy=strategy,
        hint_mode=hint_mode,
        llm_client=llm_client,
    )
    violated_rules = verify_hint_text(hint_text, plan)
    verification_passed = len(violated_rules) == 0
    notes: list[str] = []

    if not verification_passed:
        repair_result = repair_hint_text(
            problem,
            reference,
            diagnosis,
            plan,
            original_hint=hint_text,
            hint_mode=hint_mode,
            llm_client=llm_client,
        )
        repaired_violations = verify_hint_text(repair_result.hint_text, plan)
        if not repaired_violations:
            hint_text = repair_result.hint_text
            violated_rules = []
            verification_passed = True
            notes.extend(repair_result.notes)
            notes.append("used_repaired_hint")
        else:
            notes.extend(repair_result.notes)
            fallback = _fallback_hint(plan)
            fallback_violations = verify_hint_text(fallback, plan)
            if not fallback_violations:
                hint_text = fallback
                violated_rules = []
                verification_passed = True
                notes.append("used_fallback_hint")
            else:
                violated_rules = repaired_violations
                hint_text = repair_result.hint_text
                notes.append("fallback_hint_still_failed_verification")

    confidence = min(plan.confidence + (0.04 if verification_passed else -0.1), 0.97)
    confidence = max(confidence, 0.2)

    return HintResult(
        hint_text=hint_text,
        hint_level=plan.hint_level,
        hint_mode=hint_mode,
        verification_passed=verification_passed,
        violated_rules=violated_rules,
        confidence=confidence,
        notes=notes,
    )
