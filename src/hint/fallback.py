"""Static fallback hints for each diagnosis category."""
from typing import Dict
from src.models import DiagnosisLabel

FALLBACK_HINTS: Dict[DiagnosisLabel, str] = {
    DiagnosisLabel.ARITHMETIC_ERROR: "Check your arithmetic steps again. There may be a small calculation mistake.",
    DiagnosisLabel.QUANTITY_RELATION_ERROR: "Review the relationship between quantities. Should this step use add, subtract, multiply, or divide?",
    DiagnosisLabel.TARGET_MISUNDERSTANDING: "Read the question again and identify exactly which value you are asked to find.",
    DiagnosisLabel.UNPARSEABLE_ANSWER: "Please rewrite your answer in a clearer format so it can be checked.",
    DiagnosisLabel.UNKNOWN_ERROR: "Try solving again one step at a time and verify each intermediate result.",
}


def get_static_fallback_hint(label: DiagnosisLabel) -> str:
    """Retrieve a generic pedagogical hint based on the error label."""
    return FALLBACK_HINTS.get(label, "Think carefully about the problem and try one more time.")
