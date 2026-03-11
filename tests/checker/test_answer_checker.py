import pytest
from src.models import Correctness
from src.checker.answer_checker import check_answer


class TestCheckAnswer:
    def test_correct_exact(self):
        result = check_answer("18", reference_value=18.0)
        assert result.correctness == Correctness.CORRECT
        assert result.comparison_type == "exact"
        assert result.student_value == 18.0

    def test_correct_decimal_equivalent(self):
        result = check_answer("18.0", reference_value=18.0)
        assert result.correctness == Correctness.CORRECT

    def test_correct_from_text(self):
        result = check_answer("The answer is 18", reference_value=18.0)
        assert result.correctness == Correctness.CORRECT

    def test_incorrect(self):
        result = check_answer("20", reference_value=18.0)
        assert result.correctness == Correctness.INCORRECT
        assert result.student_value == 20.0

    def test_unparseable(self):
        result = check_answer("I have no idea", reference_value=18.0)
        assert result.correctness == Correctness.UNPARSEABLE
        assert result.student_value is None
        assert result.normalization_status == "failed"

    def test_reference_value_always_present(self):
        result = check_answer("42", reference_value=42.0)
        assert result.reference_value == 42.0

    def test_negative_correct(self):
        result = check_answer("-5", reference_value=-5.0)
        assert result.correctness == Correctness.CORRECT

    def test_close_but_wrong(self):
        result = check_answer("18.1", reference_value=18.0)
        assert result.correctness == Correctness.INCORRECT

    def test_empty_string_unparseable(self):
        result = check_answer("", reference_value=10.0)
        assert result.correctness == Correctness.UNPARSEABLE
