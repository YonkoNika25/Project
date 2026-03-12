"""Hint verification utilities for spoiler and pedagogical alignment checks."""
import re
import logging
from typing import Optional

from src.models import DiagnosisLabel, HintLevel

logger = logging.getLogger(__name__)


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
) -> bool:
    """Check whether hint content is pedagogically aligned with diagnosis/level."""
    if not hint_text:
        return False

    lower = hint_text.lower()

    label_keywords = {
        DiagnosisLabel.ARITHMETIC_ERROR: ["calculation", "compute", "arithmetic", "step"],
        DiagnosisLabel.QUANTITY_RELATION_ERROR: ["relationship", "between", "add", "subtract", "total"],
        DiagnosisLabel.TARGET_MISUNDERSTANDING: ["question", "asked", "target", "find", "value"],
        DiagnosisLabel.UNPARSEABLE_ANSWER: ["rewrite", "clear", "clarify", "format", "explain"],
    }

    if diagnosis_label in label_keywords:
        if not any(k in lower for k in label_keywords[diagnosis_label]):
            logger.warning("Hint failed diagnosis-label alignment for %s", diagnosis_label.value)
            return False

    if expected_level == HintLevel.RELATIONAL:
        relational_tokens = ["relationship", "between", "add", "subtract", "compare"]
        if not any(tok in lower for tok in relational_tokens):
            logger.warning("Hint failed relational-level alignment")
            return False

    if expected_level == HintLevel.NEXT_STEP:
        action_tokens = ["try", "next", "step", "then", "first"]
        if not any(tok in lower for tok in action_tokens):
            logger.warning("Hint failed next-step alignment")
            return False

    return True
