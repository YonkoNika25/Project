import pytest
from src.models import (
    DiagnosisLabel,
    HintLevel,
    DiagnosisResult,
    ErrorLocalization,
    VerificationResult,
    VerificationStatus,
)
from src.hint.policy import get_allowed_hint_levels, derive_preferred_hint_level


def _diag(
    label: DiagnosisLabel,
    confidence: float = 0.9,
    localization: ErrorLocalization = ErrorLocalization.UNKNOWN,
) -> DiagnosisResult:
    return DiagnosisResult(
        label=label,
        localization=localization,
        explanation="test explanation",
        confidence=confidence,
    )


class TestHintPolicy:
    def test_arithmetic_error_policy(self):
        levels = get_allowed_hint_levels(DiagnosisLabel.ARITHMETIC_ERROR)
        assert levels == [HintLevel.CONCEPTUAL, HintLevel.NEXT_STEP]

    def test_quantity_relation_policy(self):
        levels = get_allowed_hint_levels(DiagnosisLabel.QUANTITY_RELATION_ERROR)
        assert HintLevel.CONCEPTUAL in levels
        assert HintLevel.RELATIONAL in levels

    def test_correct_answer_policy(self):
        levels = get_allowed_hint_levels(DiagnosisLabel.CORRECT_ANSWER)
        assert levels == []

    def test_unknown_label_fallback(self):
        levels = get_allowed_hint_levels(DiagnosisLabel.UNKNOWN_ERROR)
        assert levels == [HintLevel.CONCEPTUAL]

    def test_weak_arithmetic_prefers_conceptual(self):
        level = derive_preferred_hint_level(
            diagnosis=_diag(DiagnosisLabel.ARITHMETIC_ERROR, confidence=0.4)
        )
        assert level == HintLevel.CONCEPTUAL

    def test_strong_arithmetic_with_final_computation_prefers_next_step(self):
        level = derive_preferred_hint_level(
            diagnosis=_diag(
                DiagnosisLabel.ARITHMETIC_ERROR,
                confidence=0.85,
                localization=ErrorLocalization.FINAL_COMPUTATION,
            ),
            verification_result=VerificationResult(
                status=VerificationStatus.VERIFIED,
                predicted_label=DiagnosisLabel.ARITHMETIC_ERROR,
                localization_hint=ErrorLocalization.FINAL_COMPUTATION,
                confidence=0.8,
            ),
        )
        assert level == HintLevel.NEXT_STEP

    def test_target_selection_prefers_conceptual(self):
        level = derive_preferred_hint_level(
            diagnosis=_diag(
                DiagnosisLabel.TARGET_MISUNDERSTANDING,
                localization=ErrorLocalization.TARGET_SELECTION,
            ),
            verification_result=VerificationResult(
                status=VerificationStatus.CONFLICT,
                predicted_label=DiagnosisLabel.TARGET_MISUNDERSTANDING,
                localization_hint=ErrorLocalization.TARGET_SELECTION,
                confidence=0.9,
            ),
        )
        assert level == HintLevel.CONCEPTUAL

    def test_strong_relation_conflict_prefers_relational(self):
        level = derive_preferred_hint_level(
            diagnosis=_diag(
                DiagnosisLabel.QUANTITY_RELATION_ERROR,
                localization=ErrorLocalization.COMBINING_QUANTITIES,
            ),
            verification_result=VerificationResult(
                status=VerificationStatus.CONFLICT,
                predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
                localization_hint=ErrorLocalization.COMBINING_QUANTITIES,
                confidence=0.9,
            ),
        )
        assert level == HintLevel.RELATIONAL

    def test_weak_relation_signal_falls_back_to_conceptual(self):
        level = derive_preferred_hint_level(
            diagnosis=_diag(
                DiagnosisLabel.QUANTITY_RELATION_ERROR,
                confidence=0.6,
                localization=ErrorLocalization.COMBINING_QUANTITIES,
            ),
            verification_result=VerificationResult(
                status=VerificationStatus.CONFLICT,
                predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
                localization_hint=ErrorLocalization.COMBINING_QUANTITIES,
                confidence=0.55,
            ),
        )
        assert level == HintLevel.CONCEPTUAL
