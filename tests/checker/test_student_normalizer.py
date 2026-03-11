import pytest
from src.checker.student_normalizer import normalize_student_answer


class TestNormalizeStudentAnswer:
    def test_plain_integer(self):
        val, ok = normalize_student_answer("18")
        assert ok and val == 18.0

    def test_plain_decimal(self):
        val, ok = normalize_student_answer("3.14")
        assert ok and val == 3.14

    def test_negative(self):
        val, ok = normalize_student_answer("-5")
        assert ok and val == -5.0

    def test_with_commas(self):
        val, ok = normalize_student_answer("1,234")
        assert ok and val == 1234.0

    def test_the_answer_is_format(self):
        val, ok = normalize_student_answer("The answer is 18")
        assert ok and val == 18.0

    def test_i_think_format(self):
        val, ok = normalize_student_answer("I think it's 42 dollars")
        assert ok and val == 42.0

    def test_gsm8k_format(self):
        val, ok = normalize_student_answer("Step 1: 5+3=8\n#### 8")
        assert ok and val == 8.0

    def test_multiple_numbers_takes_last(self):
        val, ok = normalize_student_answer("First 5, then add 3, so the answer is 8")
        assert ok and val == 8.0

    def test_empty_string(self):
        val, ok = normalize_student_answer("")
        assert ok is False

    def test_none_input(self):
        val, ok = normalize_student_answer(None)
        assert ok is False

    def test_no_numbers(self):
        val, ok = normalize_student_answer("I don't know the answer")
        assert ok is False

    def test_trailing_period(self):
        val, ok = normalize_student_answer("42.")
        assert ok and val == 42.0
