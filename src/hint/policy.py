"""Pedagogical hinting policy: maps diagnosis labels to allowed hint levels."""
from typing import List, Dict
from src.models import DiagnosisLabel, HintLevel


HINT_POLICY_MAP: Dict[DiagnosisLabel, List[HintLevel]] = {
    DiagnosisLabel.CORRECT_ANSWER: [],
    DiagnosisLabel.ARITHMETIC_ERROR: [HintLevel.NEXT_STEP],
    DiagnosisLabel.QUANTITY_RELATION_ERROR: [HintLevel.CONCEPTUAL, HintLevel.RELATIONAL],
    DiagnosisLabel.TARGET_MISUNDERSTANDING: [HintLevel.CONCEPTUAL],
    DiagnosisLabel.UNPARSEABLE_ANSWER: [HintLevel.CONCEPTUAL, HintLevel.NEXT_STEP],
    DiagnosisLabel.UNKNOWN_ERROR: [HintLevel.CONCEPTUAL, HintLevel.NEXT_STEP],
}


def get_allowed_hint_levels(label: DiagnosisLabel) -> List[HintLevel]:
    """Retrieve the list of allowed hint levels for a given diagnosis label.
    
    This policy ensures that hints are pedagogical and do not spoil the answer.
    """
    return HINT_POLICY_MAP.get(label, [HintLevel.CONCEPTUAL, HintLevel.NEXT_STEP])
