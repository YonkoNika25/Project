import pytest
from src.hint.verifier import verify_hint_no_spoiler

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
        # Hint has 18.0 but reference is 18
        hint = "Is the result 18.0?"
        assert verify_hint_no_spoiler(hint, 18.0) is False
        
        # Hint has 18 but reference is 18.0
        hint = "Could it be 18?"
        assert verify_hint_no_spoiler(hint, 18.0) is False

    def test_partial_number_match_not_spoiler(self):
        # Answer is 8, hint mentions 18. Should NOT be a spoiler.
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
