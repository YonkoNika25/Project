import pytest

from src.models import DiagnosisLabel, ErrorLocalization, HintLevel
from src.hint.verifier import verify_hint_alignment, verify_hint_no_spoiler


class TestVerifyHintNoSpoiler:
    def test_clean_hint(self):
        hint = "Try thinking about the number of apples John started with."
        assert verify_hint_no_spoiler(hint, 18.0) is True

    def test_spoiler_exact_int(self):
        hint = "The answer is 18."
        assert verify_hint_no_spoiler(hint, 18.0) is False

    def test_spoiler_exact_decimal(self):
        hint = "Maybe it's 3.14?"
        assert verify_hint_no_spoiler(hint, 3.14) is False

    def test_spoiler_with_commas(self):
        hint = "It's around 1,234 items."
        assert verify_hint_no_spoiler(hint, 1234.0) is False

    def test_numeric_equivalence_spoiler(self):
        hint = "Is the result 18.0?"
        assert verify_hint_no_spoiler(hint, 18.0) is False

        hint = "Could it be 18?"
        assert verify_hint_no_spoiler(hint, 18.0) is False

    def test_partial_number_match_not_spoiler(self):
        hint = "There are 18 students in total."
        assert verify_hint_no_spoiler(hint, 8.0) is True

    def test_negative_spoiler(self):
        hint = "The change is -5 dollars."
        assert verify_hint_no_spoiler(hint, -5.0) is False

    def test_empty_hint(self):
        assert verify_hint_no_spoiler("", 10.0) is True

    def test_multiple_numbers_one_is_spoiler(self):
        hint = "You had 5, added 3, and got 8."
        assert verify_hint_no_spoiler(hint, 8.0) is False
        assert verify_hint_no_spoiler(hint, 5.0) is False
        assert verify_hint_no_spoiler(hint, 10.0) is True


class TestVerifyHintAlignment:
    def test_arithmetic_alignment_pass(self):
        hint = "Try checking the calculation at the final step."
        assert (
            verify_hint_alignment(
                hint,
                DiagnosisLabel.ARITHMETIC_ERROR,
                HintLevel.NEXT_STEP,
                ErrorLocalization.FINAL_COMPUTATION,
            )
            is True
        )

    def test_arithmetic_alignment_fail(self):
        hint = "Read the question again and identify the target quantity."
        assert (
            verify_hint_alignment(
                hint,
                DiagnosisLabel.ARITHMETIC_ERROR,
                HintLevel.NEXT_STEP,
                ErrorLocalization.FINAL_COMPUTATION,
            )
            is False
        )

    def test_relational_level_requires_relational_tokens(self):
        hint = "Check the relationship between quantities before deciding whether to add or subtract."
        assert (
            verify_hint_alignment(
                hint,
                DiagnosisLabel.QUANTITY_RELATION_ERROR,
                HintLevel.RELATIONAL,
                ErrorLocalization.COMBINING_QUANTITIES,
            )
            is True
        )

    def test_next_step_level_requires_action_tokens(self):
        hint = "The relationship between the numbers is additive."
        assert (
            verify_hint_alignment(
                hint,
                DiagnosisLabel.QUANTITY_RELATION_ERROR,
                HintLevel.NEXT_STEP,
                ErrorLocalization.COMBINING_QUANTITIES,
            )
            is False
        )

    def test_natural_arithmetic_phrasing_passes(self):
        hint = "Recheck how you added the amounts before moving on."
        assert (
            verify_hint_alignment(
                hint,
                DiagnosisLabel.ARITHMETIC_ERROR,
                HintLevel.NEXT_STEP,
                ErrorLocalization.FINAL_COMPUTATION,
            )
            is True
        )

    def test_natural_target_phrasing_passes(self):
        hint = "Go back to the question and focus on what quantity it asks for."
        assert (
            verify_hint_alignment(
                hint,
                DiagnosisLabel.TARGET_MISUNDERSTANDING,
                HintLevel.CONCEPTUAL,
                ErrorLocalization.TARGET_SELECTION,
            )
            is True
        )
