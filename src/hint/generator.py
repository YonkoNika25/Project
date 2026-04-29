"""Hint generation from pedagogy plans with optional LLM support."""
from __future__ import annotations

import json

from src.llm import LLMClient, LLMGenerationError
from src.models import (
    CanonicalReference,
    FormalizedProblem,
    HintMode,
    HintPlan,
    HintStrategy,
    TeacherMove,
)


def _target_prompt(problem: FormalizedProblem) -> str:
    if problem.target is not None:
        return problem.target.surface_text.rstrip("?")
    return "what quantity the problem is asking for"


def _deterministic_hint_text(
    problem: FormalizedProblem,
    plan: HintPlan,
    strategy: HintStrategy | None = None,
) -> str:
    target_prompt = _target_prompt(problem)
    focus_points = strategy.focus_points if strategy is not None and strategy.focus_points else plan.focus_points
    student_action = strategy.student_action if strategy is not None else None

    if plan.teacher_move == TeacherMove.RESTATE_RESULT:
        return "Your answer is correct."

    if plan.teacher_move == TeacherMove.REFOCUS_TARGET:
        return (
            f"Look back at {target_prompt}. "
            "Ask yourself whether your current result is the final quantity or only an intermediate value."
        )

    if plan.teacher_move == TeacherMove.CHECK_RELATIONSHIP:
        return (
            "Before calculating again, decide how the quantities should be related. "
            + (
                f"Focus on {focus_points[0].lower()}."
                if focus_points
                else "Ask whether this step should combine, compare, or apply a rate to the values in the problem."
            )
        )

    if plan.teacher_move == TeacherMove.RECOMPUTE_STEP:
        return (
            "Recheck the arithmetic in the step you just computed. "
            "Write that calculation again carefully before you move on."
        )

    if plan.teacher_move == TeacherMove.CONTINUE_FROM_STEP:
        return (
            "Your setup looks close, so pause before the last computation. "
            + (
                student_action
                if student_action
                else "Use the quantities you already found and recompute the final step carefully."
            )
        )

    if plan.teacher_move == TeacherMove.METACOGNITIVE_PROMPT:
        return (
            f"Restate {target_prompt} in your own words. "
            "Then give one clear numeric answer."
        )

    return (
        f"Pause and think about {target_prompt}. "
        "Check what the problem is asking for before you continue."
    )


def _llm_hint_text(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    plan: HintPlan,
    strategy: HintStrategy | None,
    hint_mode: HintMode,
    llm_client: LLMClient,
) -> str:
    system_prompt = (
        "You are a math tutor. Return only a JSON object with one field: hint_text. "
        "Write at most two sentences. Follow the pedagogy plan exactly. Do not reveal any forbidden content."
    )
    user_prompt = (
        f"Problem target:\n{_target_prompt(problem)}\n\n"
        f"Hint strategy:\n{json.dumps(strategy.model_dump(mode='json'), ensure_ascii=True) if strategy is not None else 'null'}\n\n"
        f"Compatibility hint plan:\n{json.dumps(plan.model_dump(mode='json'), ensure_ascii=True)}\n\n"
        f"Reference answer (must not be revealed): {reference.final_answer:g}\n"
        f"Hint mode: {hint_mode.value}\n\n"
        "Return JSON like {\"hint_text\": \"...\"}."
    )
    payload = llm_client.generate_json(
        task_name="hint_generator",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.4,
        max_tokens=1000,
    )
    hint_text = str(payload.get("hint_text", "")).strip()
    if not hint_text:
        raise LLMGenerationError("LLM hint generator returned empty hint_text")
    return hint_text


def generate_hint_text(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    plan: HintPlan,
    strategy: HintStrategy | None = None,
    hint_mode: HintMode = HintMode.NORMAL,
    llm_client: LLMClient | None = None,
) -> str:
    """Generate a short hint from the pedagogy plan."""
    if llm_client is None:
        return _deterministic_hint_text(problem, plan, strategy=strategy)

    try:
        return _llm_hint_text(problem, reference, plan, strategy, hint_mode, llm_client)
    except (LLMGenerationError, ValueError, TypeError, KeyError):
        return _deterministic_hint_text(problem, plan, strategy=strategy)
