"""Build lightweight symbolic state from problem/reference text."""
import re
from typing import List

from src.models import SymbolicState, QuantityFact, OperationType


_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")

_ADDITIVE_CUES = (
    "total",
    "altogether",
    "in all",
    "sum",
    "more",
    "added",
    "combined",
    "together",
    "buys",
)
_SUBTRACTIVE_CUES = (
    "left",
    "remain",
    "remaining",
    "still available",
    "available",
    "difference",
    "less",
    "fewer",
    "after giving",
    "gives out",
    "gave out",
    "gave",
    "spent",
    "lost",
    "eat",
    "eaten",
    "uneaten",
)
_UNSUPPORTED_RELATION_CUES = (
    "each",
    "per",
    "times",
    "twice",
    "double",
    "triple",
    "half",
    "quarter",
    "%",
    "percent",
)


def _matching_cues(text: str, cues: tuple[str, ...]) -> List[str]:
    lower = text.lower()
    return [cue for cue in cues if cue in lower]


def _infer_operation(problem_text: str, target_text: str = "") -> tuple[OperationType, List[str]]:
    combined_text = f"{problem_text} {target_text}".strip().lower()
    add_matches = _matching_cues(combined_text, _ADDITIVE_CUES)
    sub_matches = _matching_cues(combined_text, _SUBTRACTIVE_CUES)
    unsupported_matches = _matching_cues(combined_text, _UNSUPPORTED_RELATION_CUES)

    add_score = len(add_matches)
    sub_score = len(sub_matches)

    notes: List[str] = []
    if add_matches:
        notes.append("additive_cues=" + ",".join(add_matches))
    if sub_matches:
        notes.append("subtractive_cues=" + ",".join(sub_matches))
    if unsupported_matches:
        notes.append("unsupported_relation_cues=" + ",".join(unsupported_matches))

    if add_score > sub_score:
        return OperationType.ADDITIVE, notes
    if sub_score > add_score:
        return OperationType.SUBTRACTIVE, notes

    if unsupported_matches and add_score == 0 and sub_score == 0:
        return OperationType.UNKNOWN, notes

    return OperationType.UNKNOWN, notes


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
    text = problem_text.strip()
    if not text:
        return ""

    question_match = re.search(
        r"((?:if\b.*?,\s*)?(?:how many|how much|what|which|who|where|when|why)[^?]*\?)",
        text,
        re.IGNORECASE,
    )
    if question_match:
        return question_match.group(1).strip()

    question_index = text.rfind("?")
    if question_index != -1:
        prefix = text[:question_index]
        sentence_start = 0
        for marker in (". ", "! ", "? ", "; ", ": "):
            marker_index = prefix.rfind(marker)
            if marker_index != -1:
                sentence_start = max(sentence_start, marker_index + len(marker))
        candidate = text[sentence_start:question_index + 1].strip()
        if candidate:
            return candidate
        return text[:question_index + 1].strip()

    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    if not parts:
        return text
    return parts[-1]


def build_symbolic_state(problem_text: str, reference_solution_text: str = "") -> SymbolicState:
    """Build a lightweight symbolic state for downstream verification/diagnosis."""
    quantities = _extract_quantities(problem_text)
    target_text = _extract_target_text(problem_text)
    expected_operation, operation_notes = _infer_operation(problem_text, target_text)

    notes = [f"quantities_extracted={len(quantities)}"]
    if target_text:
        notes.append("target_question_extracted")
    notes.extend(operation_notes)
    if reference_solution_text and "####" in reference_solution_text:
        notes.append("reference_has_explicit_final_marker")

    confidence = 0.15
    if quantities:
        confidence += 0.25
    if len(quantities) >= 2:
        confidence += 0.15
    if expected_operation != OperationType.UNKNOWN:
        confidence += 0.25
    if target_text:
        confidence += 0.1
    if any(note.startswith("unsupported_relation_cues=") for note in notes):
        confidence -= 0.1
    if len(quantities) > 4:
        confidence -= 0.05

    return SymbolicState(
        quantities=quantities,
        target_text=target_text or None,
        expected_operation=expected_operation,
        builder_confidence=min(confidence, 1.0),
        evidence_notes=notes,
    )
