"""Hint verification utilities for spoiler and pedagogical alignment checks."""
import logging
import re
from typing import Optional

from src.models import DiagnosisLabel, ErrorLocalization, HintLevel

logger = logging.getLogger(__name__)


def _normalize_hint_text(hint_text: str) -> str:
    lowered = hint_text.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def verify_hint_no_spoiler(hint_text: str, reference_answer: float) -> bool:
    """Verify that the hint text does not contain the final reference answer."""
    if not hint_text:
        return True

    ref_str = str(reference_answer)
    potential_matches = [ref_str]
    if ref_str.endswith(".0"):
        int_version = ref_str[:-2]
        potential_matches.append(int_version)
        if reference_answer >= 1000:
            comma_version = "{:,}".format(int(reference_answer))
            potential_matches.append(comma_version)

    for match in potential_matches:
        pattern = r"(?<![\d,.])" + re.escape(match) + r"(?![\d,.])"
        if re.search(pattern, hint_text):
            logger.warning("Spoiler detected in hint! Match: %s", match)
            return False

    found_numbers = re.findall(r"-?\d[\d,]*\.?\d*", hint_text)
    for num_str in found_numbers:
        try:
            val = float(num_str.replace(",", ""))
            if abs(val - reference_answer) < 1e-9:
                logger.warning("Spoiler detected in hint! Numeric match: %f", val)
                return False
        except ValueError:
            continue

    return True


def verify_hint_alignment(
    hint_text: str,
    diagnosis_label: DiagnosisLabel,
    expected_level: Optional[HintLevel] = None,
    diagnosis_localization: Optional[ErrorLocalization] = None,
) -> bool:
    """Check whether hint content is pedagogically aligned with diagnosis/level."""
    if not hint_text:
        return False

    normalized = _normalize_hint_text(hint_text)

    label_keywords = {
        DiagnosisLabel.ARITHMETIC_ERROR: [
            "calculation",
            "compute",
            "arithmetic",
            "check your math",
            "recheck",
            "work out",
            "added",
            "adding",
            "subtracted",
            "subtracting",
            "multiplied",
            "divided",
            "count again",
        ],
        DiagnosisLabel.QUANTITY_RELATION_ERROR: [
            "relationship",
            "relate",
            "between",
            "add",
            "subtract",
            "combine",
            "compare",
            "difference",
            "total",
            "in all",
            "left",
            "remain",
        ],
        DiagnosisLabel.TARGET_MISUNDERSTANDING: [
            "question",
            "asked",
            "asking",
            "asks for",
            "target",
            "find",
            "what value",
            "which value",
            "what quantity",
            "which quantity",
            "looking for",
        ],
        DiagnosisLabel.UNPARSEABLE_ANSWER: [
            "rewrite",
            "clear",
            "clarify",
            "format",
            "explain",
            "write your answer",
            "typed",
        ],
    }

    if diagnosis_label in label_keywords:
        if not _contains_any(normalized, label_keywords[diagnosis_label]):
            logger.warning("Hint failed diagnosis-label alignment for %s", diagnosis_label.value)
            return False

    if diagnosis_localization == ErrorLocalization.TARGET_SELECTION:
        target_tokens = ["question", "asks for", "what quantity", "which value", "looking for"]
        if not _contains_any(normalized, target_tokens):
            logger.warning("Hint failed target-selection alignment")
            return False

    if diagnosis_localization == ErrorLocalization.COMBINING_QUANTITIES:
        relation_tokens = ["relationship", "combine", "compare", "add", "subtract", "total", "difference"]
        if not _contains_any(normalized, relation_tokens):
            logger.warning("Hint failed combining-quantities alignment")
            return False

    if diagnosis_localization == ErrorLocalization.FINAL_COMPUTATION:
        computation_tokens = [
            "calculate",
            "calculation",
            "recheck",
            "check your math",
            "count again",
            "compute",
            "adding",
            "added",
            "subtracting",
            "subtracted",
            "multiplying",
            "dividing",
            "last step",
        ]
        if not _contains_any(normalized, computation_tokens):
            logger.warning("Hint failed final-computation alignment")
            return False

    if expected_level == HintLevel.RELATIONAL:
        relational_tokens = ["relationship", "between", "add", "subtract", "compare", "combine", "difference"]
        if not _contains_any(normalized, relational_tokens):
            logger.warning("Hint failed relational-level alignment")
            return False

    if expected_level == HintLevel.NEXT_STEP:
        action_tokens = [
            "try",
            "next",
            "step",
            "then",
            "first",
            "start by",
            "begin by",
            "go back",
            "recheck",
            "check",
            "look at",
        ]
        starts_with_action = re.match(
            r"^(try|first|next|then|start|begin|check|look|go back|recheck)\b",
            normalized,
        )
        if not _contains_any(normalized, action_tokens) and not starts_with_action:
            logger.warning("Hint failed next-step alignment")
            return False

    return True
