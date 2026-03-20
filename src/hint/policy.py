"""Pedagogical hinting policy driven by diagnosis confidence and symbolic evidence."""
from typing import List, Dict, Optional

from src.models import (
    DiagnosisLabel,
    HintLevel,
    DiagnosisResult,
    VerificationResult,
    VerificationStatus,
    ErrorLocalization,
)


HINT_POLICY_MAP: Dict[DiagnosisLabel, List[HintLevel]] = {
    DiagnosisLabel.CORRECT_ANSWER: [],
    DiagnosisLabel.ARITHMETIC_ERROR: [HintLevel.CONCEPTUAL, HintLevel.NEXT_STEP],
    DiagnosisLabel.QUANTITY_RELATION_ERROR: [HintLevel.CONCEPTUAL, HintLevel.RELATIONAL],
    DiagnosisLabel.TARGET_MISUNDERSTANDING: [HintLevel.CONCEPTUAL],
    DiagnosisLabel.UNPARSEABLE_ANSWER: [HintLevel.CONCEPTUAL],
    DiagnosisLabel.UNKNOWN_ERROR: [HintLevel.CONCEPTUAL],
}


def get_allowed_hint_levels(label: DiagnosisLabel) -> List[HintLevel]:
    """Retrieve the list of allowed hint levels for a given diagnosis label.
    
    This policy ensures that hints are pedagogical and do not spoil the answer.
    """
    return HINT_POLICY_MAP.get(label, [HintLevel.CONCEPTUAL])


def _first_allowed(allowed_levels: List[HintLevel]) -> Optional[HintLevel]:
    return allowed_levels[0] if allowed_levels else None


def derive_preferred_hint_level(
    diagnosis: DiagnosisResult,
    verification_result: Optional[VerificationResult] = None,
    preferred_level: Optional[HintLevel] = None,
) -> Optional[HintLevel]:
    """Choose the safest useful hint level from diagnosis and verification evidence."""
    allowed_levels = get_allowed_hint_levels(diagnosis.label)
    if not allowed_levels:
        return None

    if preferred_level in allowed_levels:
        return preferred_level

    if diagnosis.confidence < 0.5:
        return HintLevel.CONCEPTUAL if HintLevel.CONCEPTUAL in allowed_levels else _first_allowed(allowed_levels)

    if verification_result is not None:
        if verification_result.status == VerificationStatus.INSUFFICIENT_EVIDENCE:
            return HintLevel.CONCEPTUAL if HintLevel.CONCEPTUAL in allowed_levels else _first_allowed(allowed_levels)

        if verification_result.localization_hint == ErrorLocalization.TARGET_SELECTION:
            return HintLevel.CONCEPTUAL if HintLevel.CONCEPTUAL in allowed_levels else _first_allowed(allowed_levels)

        if verification_result.localization_hint == ErrorLocalization.COMBINING_QUANTITIES:
            strong_relation_signal = (
                verification_result.status == VerificationStatus.CONFLICT
                and verification_result.confidence >= 0.75
            )
            if strong_relation_signal and HintLevel.RELATIONAL in allowed_levels:
                return HintLevel.RELATIONAL
            return HintLevel.CONCEPTUAL if HintLevel.CONCEPTUAL in allowed_levels else _first_allowed(allowed_levels)

        if verification_result.localization_hint == ErrorLocalization.FINAL_COMPUTATION:
            arithmetic_ready = (
                diagnosis.label == DiagnosisLabel.ARITHMETIC_ERROR
                and verification_result.status == VerificationStatus.VERIFIED
                and verification_result.confidence >= 0.7
            )
            if arithmetic_ready and HintLevel.NEXT_STEP in allowed_levels:
                return HintLevel.NEXT_STEP

    if diagnosis.label == DiagnosisLabel.ARITHMETIC_ERROR and HintLevel.NEXT_STEP in allowed_levels:
        if diagnosis.confidence >= 0.75:
            return HintLevel.NEXT_STEP

    if diagnosis.label == DiagnosisLabel.QUANTITY_RELATION_ERROR:
        if diagnosis.confidence >= 0.65 and HintLevel.RELATIONAL in allowed_levels:
            return HintLevel.RELATIONAL
        return HintLevel.CONCEPTUAL if HintLevel.CONCEPTUAL in allowed_levels else _first_allowed(allowed_levels)

    if diagnosis.label == DiagnosisLabel.TARGET_MISUNDERSTANDING:
        return HintLevel.CONCEPTUAL if HintLevel.CONCEPTUAL in allowed_levels else _first_allowed(allowed_levels)

    return HintLevel.CONCEPTUAL if HintLevel.CONCEPTUAL in allowed_levels else _first_allowed(allowed_levels)
