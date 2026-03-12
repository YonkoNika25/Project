"""GSM8K/solver answer parser: extracts final numeric answer from model output."""
import re
from typing import Optional, Tuple


_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")
_ANSWER_CUE_PATTERN = re.compile(
    r"(?:final\s+answer|answer\s+is|therefore|thus|so\s+the\s+answer\s+is)\s*[:=]?\s*([-?\d][\d,]*\.?\d*)",
    re.IGNORECASE,
)


def _to_float(number_text: str) -> Optional[float]:
    cleaned = number_text.strip().replace(",", "").rstrip(".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except (ValueError, OverflowError):
        return None


def parse_gsm8k_answer(answer_text: str) -> Tuple[Optional[float], bool]:
    """Parse model/dataset answer text into a numeric value.

    Priority order:
    1. Strict GSM8K marker: ``#### <number>``
    2. Common answer cues: ``answer is <number>``, ``final answer: <number>``
    3. Fallback to the last numeric token in the text
    """
    if not answer_text or not isinstance(answer_text, str):
        return None, False

    # 1) Strict GSM8K format (allowing noise like $)
    hash_match = re.search(r"####\s*(.*?)$", answer_text, re.MULTILINE)
    if hash_match:
        # Extract the first valid number from the text after ####
        nums = _NUMBER_PATTERN.findall(hash_match.group(1))
        if nums:
            value = _to_float(nums[-1])
            return (value, True) if value is not None else (None, False)

    # 2) Common LLM answer cues
    cue_match = _ANSWER_CUE_PATTERN.search(answer_text)
    if cue_match:
        value = _to_float(cue_match.group(1))
        return (value, True) if value is not None else (None, False)

    # 3) Last-number fallback for non-compliant generations
    numbers = _NUMBER_PATTERN.findall(answer_text)
    if not numbers:
        return None, False

    value = _to_float(numbers[-1])
    return (value, True) if value is not None else (None, False)
