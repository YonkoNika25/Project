"""Verification utilities for generated hints."""
from __future__ import annotations

import re

from src.models import HintPlan, TeacherMove


_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")
_TOKEN_PATTERN = re.compile(r"[a-z]+")
_CONTENT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
    "by",
    "for",
    "from",
    "give",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "re",
    "the",
    "then",
    "this",
    "to",
    "use",
    "what",
    "which",
    "your",
}


def _normalize(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(_normalize(text))
        if token not in _CONTENT_STOPWORDS and len(token) >= 3
    }


def _safe_focus_points(plan: HintPlan) -> list[str]:
    hidden_tokens = set().union(*[_content_tokens(item) for item in plan.must_not_reveal if item.strip()]) if plan.must_not_reveal else set()
    safe_points: list[str] = []
    for point in plan.focus_points:
        tokens = _content_tokens(point)
        if not tokens or tokens.issubset(hidden_tokens):
            continue
        safe_points.append(point)
    return safe_points


def check_no_spoiler(hint_text: str, plan: HintPlan) -> list[str]:
    """Return spoiler violations found in the hint text."""
    violations: list[str] = []
    normalized_hint = _normalize(hint_text)
    hint_numbers = {match.replace(",", "") for match in _NUMBER_PATTERN.findall(hint_text)}

    for hidden in plan.must_not_reveal:
        normalized_hidden = _normalize(hidden)
        if not normalized_hidden:
            continue
        if _NUMBER_PATTERN.fullmatch(hidden.replace(",", "")):
            if hidden.replace(",", "") in hint_numbers:
                violations.append(f"reveals_hidden_number:{hidden}")
            continue
        if normalized_hidden in normalized_hint:
            violations.append(f"reveals_hidden_text:{hidden}")
            continue
        hidden_tokens = _content_tokens(hidden)
        hint_tokens = _content_tokens(hint_text)
        if len(hidden_tokens) >= 2 and hidden_tokens.issubset(hint_tokens):
            violations.append(f"reveals_hidden_semantics:{hidden}")

    return violations


def check_alignment(hint_text: str, plan: HintPlan) -> list[str]:
    """Return alignment violations for the generated hint."""
    violations: list[str] = []
    normalized_hint = _normalize(hint_text)
    sentence_count = len([segment for segment in re.split(r"[.!?]+", hint_text) if segment.strip()])

    semantic_cue_map = {
        TeacherMove.REFOCUS_TARGET: {"question", "target", "quantity", "intermediate", "final", "find"},
        TeacherMove.CHECK_RELATIONSHIP: {"combine", "compare", "relationship", "related", "rate", "setup"},
        TeacherMove.RECOMPUTE_STEP: {"recheck", "recompute", "calculation", "arithmetic", "carefully"},
        TeacherMove.CONTINUE_FROM_STEP: {"final", "last", "continue", "next", "step", "recompute"},
        TeacherMove.RESTATE_RESULT: {"correct"},
        TeacherMove.METACOGNITIVE_PROMPT: {"restate", "words", "numeric", "answer", "asking"},
    }
    hint_tokens = _content_tokens(hint_text)
    expected_tokens = semantic_cue_map.get(plan.teacher_move, set())
    focus_tokens = set().union(*[_content_tokens(point) for point in _safe_focus_points(plan)]) if plan.focus_points else set()

    if expected_tokens and not (expected_tokens.intersection(hint_tokens) or focus_tokens.intersection(hint_tokens)):
        violations.append("teacher_move_alignment_failed")

    if focus_tokens and not focus_tokens.intersection(hint_tokens):
        violations.append("focus_point_alignment_failed")

    if plan.hint_level.value == "conceptual" and "calculate" in normalized_hint and plan.disclosure_budget <= 1:
        violations.append("conceptual_hint_too_computational")

    if sentence_count > 2:
        violations.append("hint_too_long")

    return violations


def verify_hint_text(hint_text: str, plan: HintPlan) -> list[str]:
    """Return the combined verification violations for a hint."""
    return check_no_spoiler(hint_text, plan) + check_alignment(hint_text, plan)
