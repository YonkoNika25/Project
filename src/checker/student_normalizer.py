"""Student answer normalizer: extracts numeric values from free-text student responses."""
import re
from typing import Optional, Tuple


def normalize_student_answer(raw_answer: str) -> Tuple[Optional[float], bool]:
    """Extract a numeric answer from a student's free-text response.

    Handles formats like:
      - "18"
      - "18.0"
      - "The answer is 18"
      - "I think it's 18 dollars"
      - "#### 18"
      - "-5.5"
      - "1,234"

    Args:
        raw_answer: Raw student answer text.

    Returns:
        Tuple of (numeric_value, success).
    """
    if not raw_answer or not isinstance(raw_answer, str):
        return None, False

    text = raw_answer.strip()

    # Try #### pattern first (GSM8K style)
    match = re.search(r"####\s*(.+)$", text, re.MULTILINE)
    if match:
        candidate = match.group(1).strip().replace(",", "").rstrip(".")
        try:
            return float(candidate), True
        except ValueError:
            pass

    # Try to find the last number in the text (most plausible final answer)
    # Match integers, decimals, negative numbers, comma-separated
    numbers = re.findall(r"-?\d[\d,]*\.?\d*", text)

    if numbers:
        # Take the last number found (most likely the final answer)
        candidate = numbers[-1].replace(",", "")
        try:
            return float(candidate), True
        except ValueError:
            pass

    # Try the whole string as a number
    cleaned = text.replace(",", "").rstrip(".").strip()
    try:
        return float(cleaned), True
    except ValueError:
        pass

    return None, False
