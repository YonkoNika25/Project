"""Build lightweight symbolic state from problem/reference text."""
import re
from typing import List

from src.models import SymbolicState, QuantityFact, OperationType


_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")


def _infer_operation(problem_text: str) -> OperationType:
    lower = problem_text.lower()
    add_cues = ["total", "altogether", "in all", "sum", "more", "buys", "added"]
    sub_cues = ["left", "remain", "difference", "less", "fewer", "after giving", "spent"]

    add_score = sum(1 for cue in add_cues if cue in lower)
    sub_score = sum(1 for cue in sub_cues if cue in lower)

    if add_score > sub_score:
        return OperationType.ADDITIVE
    if sub_score > add_score:
        return OperationType.SUBTRACTIVE
    return OperationType.UNKNOWN


def _extract_quantities(problem_text: str) -> List[QuantityFact]:
    facts: List[QuantityFact] = []
    for token in _NUMBER_PATTERN.findall(problem_text):
        normalized = token.replace(",", "")
        try:
            facts.append(QuantityFact(surface_form=token, value=float(normalized)))
        except ValueError:
            continue
    return facts


def _extract_target_text(problem_text: str) -> str:
    parts = [p.strip() for p in problem_text.split("?") if p.strip()]
    if not parts:
        return ""
    return parts[-1]


def build_symbolic_state(problem_text: str, reference_solution_text: str = "") -> SymbolicState:
    """Build a lightweight symbolic state for downstream verification/diagnosis."""
    quantities = _extract_quantities(problem_text)
    expected_operation = _infer_operation(problem_text)
    target_text = _extract_target_text(problem_text)

    notes = [f"quantities_extracted={len(quantities)}"]
    if reference_solution_text and "####" in reference_solution_text:
        notes.append("reference_has_explicit_final_marker")

    confidence = 0.2
    if quantities:
        confidence += 0.4
    if expected_operation != OperationType.UNKNOWN:
        confidence += 0.3
    if target_text:
        confidence += 0.1

    return SymbolicState(
        quantities=quantities,
        target_text=target_text or None,
        expected_operation=expected_operation,
        builder_confidence=min(confidence, 1.0),
        evidence_notes=notes,
    )
