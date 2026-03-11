"""Rule-based hint verification: ensures hints do not disclose the final answer."""
import re
import logging

logger = logging.getLogger(__name__)

def verify_hint_no_spoiler(hint_text: str, reference_answer: float) -> bool:
    """Verify that the hint text does not contain the final reference answer.

    This acts as a safety guardrail to prevents spoilers. It checks for:
    - The exact numeric value as a string.
    - The value with commas (e.g. 1,000).
    - Numeric equivalence for all numbers found in the text.

    Args:
        hint_text: The generated hint string.
        reference_answer: The correct numeric answer.

    Returns:
        True if the hint is clean (no spoiler), False if it contains the answer.
    """
    if not hint_text:
        return True

    # 1. Check for the string representation of the reference answer
    ref_str = str(reference_answer)
    # If it ends in .0, also check the integer version
    potential_matches = [ref_str]
    if ref_str.endswith(".0"):
        int_version = ref_str[:-2]
        potential_matches.append(int_version)
        # Also with commas if > 1000
        if reference_answer >= 1000:
            comma_version = "{:,}".format(int(reference_answer))
            potential_matches.append(comma_version)

    for match in potential_matches:
        # Use word boundaries to avoid partial matches (e.g. answer 8 in "18")
        # However, for numbers with decimals, word boundaries can be tricky.
        # We'll use a regex that matches numbers specifically.
        pattern = r"(?<![\d,.])" + re.escape(match) + r"(?![\d,.])"
        if re.search(pattern, hint_text):
            logger.warning("Spoiler detected in hint! Match: %s", match)
            return False

    # 2. More robust: extract all numbers and compare numerically
    # This handles things like "18.0" vs "18" vs "18.00"
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
