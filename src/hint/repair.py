"""Hint repair utilities for pedagogy-aligned post-processing."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.hint.verifier import check_alignment, check_no_spoiler
from src.llm import LLMClient, LLMGenerationError
from src.models import (
    CanonicalReference,
    DiagnosisResult,
    FormalizedProblem,
    HintMode,
    HintPlan,
    TeacherMove,
)


_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")


@dataclass
class HintRepairResult:
    hint_text: str
    notes: list[str]


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", _normalize_whitespace(text))
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _join_sentences(sentences: list[str], limit: int = 2) -> str:
    trimmed = [sentence.rstrip() for sentence in sentences[:limit] if sentence.strip()]
    return " ".join(trimmed).strip()


def _remove_hidden_content(text: str, plan: HintPlan) -> str:
    repaired = text
    for hidden in sorted(plan.must_not_reveal, key=len, reverse=True):
        if not hidden.strip():
            continue

        hidden_number = hidden.replace(",", "")
        if _NUMBER_PATTERN.fullmatch(hidden_number):
            repaired = re.sub(
                rf"(?<!\w){re.escape(hidden)}(?!\w)",
                "that value",
                repaired,
                flags=re.IGNORECASE,
            )
            continue

        repaired = re.sub(re.escape(hidden), "", repaired, flags=re.IGNORECASE)

    repaired = re.sub(r"\(\s*\)", "", repaired)
    repaired = re.sub(r"\s+([,.;:!?])", r"\1", repaired)
    repaired = re.sub(r"\s{2,}", " ", repaired)
    return repaired.strip(" ,;:-")


def _safe_focus_points(plan: HintPlan) -> list[str]:
    safe_points: list[str] = []
    lowered_hidden = [hidden.lower() for hidden in plan.must_not_reveal if hidden.strip()]

    for focus_point in plan.focus_points:
        normalized = _normalize_whitespace(focus_point)
        if not normalized:
            continue
        if any(hidden in normalized.lower() for hidden in lowered_hidden):
            continue
        safe_points.append(normalized)
    return safe_points


def _teacher_move_rewrite(problem: FormalizedProblem, plan: HintPlan) -> str:
    target_prompt = (
        problem.target.surface_text.rstrip("?")
        if problem.target is not None and problem.target.surface_text.strip()
        else "what the question asks you to find"
    )
    safe_focus = _safe_focus_points(plan)
    focus_fragment = safe_focus[0] if safe_focus else ""

    if plan.teacher_move == TeacherMove.RESTATE_RESULT:
        return "Your answer is correct."

    if plan.teacher_move == TeacherMove.REFOCUS_TARGET:
        return (
            f"Read the question again: {target_prompt}. "
            "Decide whether your current result is the final quantity or only an intermediate result."
        )

    if plan.teacher_move == TeacherMove.CHECK_RELATIONSHIP:
        second_sentence = (
            f"Focus on {focus_fragment.lower()}."
            if focus_fragment
            else "Think about whether the quantities should be combined, compared, or used in a rate."
        )
        return f"Before calculating again, decide how the quantities are related. {second_sentence}"

    if plan.teacher_move == TeacherMove.RECOMPUTE_STEP:
        second_sentence = (
            f"Use {focus_fragment.lower()} as your checkpoint."
            if focus_fragment
            else "Rewrite that calculation carefully before you continue."
        )
        return f"Your setup looks close, so recheck that arithmetic step carefully. {second_sentence}"

    if plan.teacher_move == TeacherMove.CONTINUE_FROM_STEP:
        second_sentence = (
            f"Use {focus_fragment.lower()} to guide the last step."
            if focus_fragment
            else "Use the quantities you already found and recompute the last step carefully."
        )
        return f"Your setup looks close, so pause before the final computation. {second_sentence}"

    if plan.teacher_move == TeacherMove.METACOGNITIVE_PROMPT:
        second_sentence = (
            f"Keep your focus on {focus_fragment.lower()}."
            if focus_fragment
            else "Then give one clear numeric answer."
        )
        return f"Restate {target_prompt} in your own words. {second_sentence}"

    return f"Pause and think about {target_prompt}. Check what the problem is asking for before you continue."


def _minimal_repair_text(original_hint: str, plan: HintPlan) -> str:
    repaired = _remove_hidden_content(original_hint, plan)
    sentences = _split_sentences(repaired)
    if not sentences:
        return ""

    candidate = _join_sentences(sentences, limit=2)
    normalized_candidate = candidate.lower()

    if plan.teacher_move == TeacherMove.REFOCUS_TARGET and not any(
        cue in normalized_candidate for cue in ("question", "asking", "quantity", "intermediate", "final")
    ):
        candidate = _join_sentences(sentences[:1] + ["Read the question again and decide what you still need to find."], limit=2)
    elif plan.teacher_move == TeacherMove.CHECK_RELATIONSHIP and not any(
        cue in normalized_candidate for cue in ("combine", "compare", "rate", "relationship")
    ):
        candidate = _join_sentences(sentences[:1] + ["Think about how the quantities should be related before you calculate."], limit=2)
    elif plan.teacher_move == TeacherMove.RECOMPUTE_STEP and not any(
        cue in normalized_candidate for cue in ("recheck", "carefully", "step", "calculation")
    ):
        candidate = _join_sentences(sentences[:1] + ["Recheck that calculation carefully before moving on."], limit=2)
    elif plan.teacher_move == TeacherMove.CONTINUE_FROM_STEP and not any(
        cue in normalized_candidate for cue in ("final", "step", "recompute", "setup")
    ):
        candidate = _join_sentences(sentences[:1] + ["Use the values you already found and recompute the final step carefully."], limit=2)
    elif plan.teacher_move == TeacherMove.METACOGNITIVE_PROMPT and not any(
        cue in normalized_candidate for cue in ("restate", "own words", "numeric answer")
    ):
        candidate = _join_sentences(sentences[:1] + ["Restate the question in your own words, then give one clear numeric answer."], limit=2)

    if plan.hint_level.value == "conceptual" and plan.disclosure_budget <= 1:
        candidate = re.sub(r"\bcalculate\b", "think", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\bcompute\b", "reason", candidate, flags=re.IGNORECASE)

    return _normalize_whitespace(candidate)


def _llm_repair_text(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    plan: HintPlan,
    hint_mode: HintMode,
    original_hint: str,
    violated_rules: list[str],
    llm_client: LLMClient,
) -> str:
    system_prompt = (
        "You repair math tutoring hints. Return only a JSON object with one field: hint_text. "
        "Keep the hint to at most two sentences. Preserve the intended teacher move. "
        "Remove spoilers and forbidden content. If the original hint is unusable, rewrite a safe hint from scratch."
    )
    user_prompt = (
        f"Problem target:\n{problem.target.surface_text if problem.target is not None else 'unknown target'}\n\n"
        f"Original hint:\n{original_hint}\n\n"
        f"Violations:\n{json.dumps(violated_rules, ensure_ascii=True)}\n\n"
        f"Diagnosis:\n{json.dumps(diagnosis.model_dump(mode='json'), ensure_ascii=True)}\n\n"
        f"Pedagogy plan:\n{json.dumps(plan.model_dump(mode='json'), ensure_ascii=True)}\n\n"
        f"Reference answer (must not be revealed): {reference.final_answer:g}\n"
        f"Hint mode: {hint_mode.value}\n\n"
        "Return JSON like {\"hint_text\": \"...\"}."
    )
    payload = llm_client.generate_json(
        task_name="hint_repair",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.2,
        max_tokens=1000,
    )
    hint_text = str(payload.get("hint_text", "")).strip()
    if not hint_text:
        raise LLMGenerationError("LLM hint repair returned empty hint_text")
    return hint_text


def repair_hint_text(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    plan: HintPlan,
    original_hint: str,
    hint_mode: HintMode = HintMode.NORMAL,
    llm_client: LLMClient | None = None,
) -> HintRepairResult:
    """Repair a generated hint before falling back to a generic safe hint."""
    minimal_candidate = _minimal_repair_text(original_hint, plan)
    if minimal_candidate:
        minimal_violations = check_no_spoiler(minimal_candidate, plan) + check_alignment(minimal_candidate, plan)
        if not minimal_violations:
            return HintRepairResult(
                hint_text=minimal_candidate,
                notes=["hint_repair_attempted", "hint_repair:minimal_edit"],
            )

    rewrite_candidate = _teacher_move_rewrite(problem, plan)
    rewrite_violations = check_no_spoiler(rewrite_candidate, plan) + check_alignment(rewrite_candidate, plan)
    if not rewrite_violations:
        return HintRepairResult(
            hint_text=rewrite_candidate,
            notes=["hint_repair_attempted", "hint_repair:guided_rewrite"],
        )

    if llm_client is not None:
        try:
            llm_candidate = _llm_repair_text(
                problem,
                reference,
                diagnosis,
                plan,
                hint_mode,
                original_hint,
                rewrite_violations,
                llm_client,
            )
            return HintRepairResult(
                hint_text=llm_candidate,
                notes=["hint_repair_attempted", "hint_repair:llm_rewrite"],
            )
        except (LLMGenerationError, ValueError, TypeError, KeyError):
            pass

    return HintRepairResult(
        hint_text=rewrite_candidate,
        notes=["hint_repair_attempted", "hint_repair_unresolved"],
    )
