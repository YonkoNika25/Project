import pytest
from src.dataset.answer_parser import parse_gsm8k_answer


class TestParseGsm8kAnswer:
    def test_simple_integer(self):
        val, ok = parse_gsm8k_answer("Some reasoning.\n#### 18")
        assert ok is True
        assert val == 18.0

    def test_integer_with_comma(self):
        val, ok = parse_gsm8k_answer("Work shown.\n#### 1,234")
        assert ok is True
        assert val == 1234.0

    def test_negative_number(self):
        val, ok = parse_gsm8k_answer("#### -5")
        assert ok is True
        assert val == -5.0

    def test_decimal_number(self):
        val, ok = parse_gsm8k_answer("#### 3.14")
        assert ok is True
        assert val == 3.14

    def test_large_comma_number(self):
        val, ok = parse_gsm8k_answer("#### 1,000,000")
        assert ok is True
        assert val == 1_000_000.0

    def test_answer_with_trailing_period(self):
        val, ok = parse_gsm8k_answer("#### 42.")
        assert ok is True
        assert val == 42.0

    def test_cue_answer_is(self):
        val, ok = parse_gsm8k_answer("The answer is 18")
        assert ok is True
        assert val == 18.0

    def test_cue_final_answer(self):
        val, ok = parse_gsm8k_answer("After solving, Final Answer: 27")
        assert ok is True
        assert val == 27.0

    def test_last_number_fallback(self):
        val, ok = parse_gsm8k_answer("I computed 3 + 5 = 8")
        assert ok is True
        assert val == 8.0

    def test_empty_string(self):
        val, ok = parse_gsm8k_answer("")
        assert ok is False
        assert val is None

    def test_none_input(self):
        val, ok = parse_gsm8k_answer(None)
        assert ok is False
        assert val is None

    def test_malformed_number(self):
        val, ok = parse_gsm8k_answer("#### abc")
        assert ok is False
        assert val is None

    def test_multiline_reasoning(self):
        text = "Step 1: 5+3=8\nStep 2: 8*2=16\n#### 16"
        val, ok = parse_gsm8k_answer(text)
        assert ok is True
        assert val == 16.0

    def test_whitespace_around_number(self):
        val, ok = parse_gsm8k_answer("####   42  ")
        assert ok is True
        assert val == 42.0

    def test_no_number(self):
        val, ok = parse_gsm8k_answer("I cannot solve this")
        assert ok is False
        assert val is None
