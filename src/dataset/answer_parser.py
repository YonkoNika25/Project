"""GSM8K answer parser: extracts numeric gold answer from GSM8K answer format."""
import re
from typing import Optional, Tuple


def parse_gsm8k_answer(answer_text: str) -> Tuple[Optional[float], bool]:
    """Parse the GSM8K answer field to extract the numeric gold answer.

    GSM8K answers end with '#### <number>'. This function extracts and
    normalises that number.

    Args:
        answer_text: Raw answer string from GSM8K dataset.

    Returns:
        Tuple of (numeric_value, success).
        On failure numeric_value is None and success is False.
    """
    if not answer_text or not isinstance(answer_text, str):
        return None, False

    # Look for the #### pattern
    match = re.search(r"####\s*(.+)$", answer_text, re.MULTILINE)
    if not match:
        return None, False

    raw_number = match.group(1).strip()

    # Remove commas (e.g. "1,234" -> "1234")
    raw_number = raw_number.replace(",", "")

    # Remove trailing period if present
    raw_number = raw_number.rstrip(".")

    try:
        value = float(raw_number)
        return value, True
    except (ValueError, OverflowError):
        return None, False
