import pytest
from src.models import DiagnosisLabel, HintLevel
from src.hint.policy import get_allowed_hint_levels


class TestHintPolicy:
    def test_arithmetic_error_policy(self):
        levels = get_allowed_hint_levels(DiagnosisLabel.ARITHMETIC_ERROR)
        assert levels == [HintLevel.NEXT_STEP]

    def test_quantity_relation_policy(self):
        levels = get_allowed_hint_levels(DiagnosisLabel.QUANTITY_RELATION_ERROR)
        assert HintLevel.CONCEPTUAL in levels
        assert HintLevel.RELATIONAL in levels

    def test_correct_answer_policy(self):
        levels = get_allowed_hint_levels(DiagnosisLabel.CORRECT_ANSWER)
        assert levels == []

    def test_unknown_label_fallback(self):
        levels = get_allowed_hint_levels(DiagnosisLabel.UNKNOWN_ERROR)
        assert HintLevel.CONCEPTUAL in levels
        assert HintLevel.NEXT_STEP in levels
