import pytest
from pydantic import ValidationError
from src.models.schemas import ProblemRecord, NormalizedAnswer, ReferenceSolution


# ── ProblemRecord ─────────────────────────────────────────────

class TestProblemRecord:
    def test_valid(self):
        record = ProblemRecord(
            id="gsm8k_0001",
            problem="Juan has 5 apples. He buys 3 more. How many apples does he have?",
            gold_answer_text="#### 8",
            gold_answer_value=8.0,
            metadata={"source": "gsm8k", "split": "train"},
        )
        assert record.id == "gsm8k_0001"
        assert record.gold_answer_value == 8.0
        assert record.metadata["split"] == "train"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ProblemRecord(id="gsm8k_0001", problem="Missing answers")

    def test_invalid_type_gold_answer_value(self):
        with pytest.raises(ValidationError):
            ProblemRecord(
                id="gsm8k_0001",
                problem="Text",
                gold_answer_text="#### 8",
                gold_answer_value="not-a-number",
                metadata={},
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            ProblemRecord(
                id="gsm8k_0001",
                problem="Text",
                gold_answer_text="#### 8",
                gold_answer_value=8.0,
                extra_field="should fail",
            )

    def test_default_metadata(self):
        record = ProblemRecord(
            id="gsm8k_0002",
            problem="A problem",
            gold_answer_text="#### 5",
            gold_answer_value=5.0,
        )
        assert record.metadata == {}


# ── NormalizedAnswer ──────────────────────────────────────────

class TestNormalizedAnswer:
    def test_valid_parsed(self):
        ans = NormalizedAnswer(is_parsed=True, raw_text="The answer is 12.", value=12.0)
        assert ans.is_parsed is True
        assert ans.value == 12.0

    def test_valid_unparsed(self):
        ans = NormalizedAnswer(is_parsed=False, raw_text="Cannot determine")
        assert ans.is_parsed is False
        assert ans.value is None

    def test_parsed_true_missing_value_raises(self):
        with pytest.raises(ValidationError, match="Numeric value must be provided"):
            NormalizedAnswer(is_parsed=True, raw_text="Cannot determine")

    def test_parsed_false_with_value_raises(self):
        with pytest.raises(ValidationError, match="Numeric value should not be provided"):
            NormalizedAnswer(is_parsed=False, raw_text="Some text", value=5.0)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            NormalizedAnswer(is_parsed=True, raw_text="12", value=12.0, extra="bad")


# ── ReferenceSolution ─────────────────────────────────────────

class TestReferenceSolution:
    VALID_DATA = {
        "final_answer": 42.0,
        "solution_text": "The meaning of life.",
        "confidence": 0.95,
        "schema_version": "1.0",
        "source": "qwen2.5-math",
        "structured_trace": {"steps": 1},
    }

    def test_valid(self):
        sol = ReferenceSolution(**self.VALID_DATA)
        assert sol.final_answer == 42.0
        assert sol.confidence == 0.95
        assert sol.source == "qwen2.5-math"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ReferenceSolution(final_answer=42.0)

    def test_confidence_above_1_raises(self):
        data = {**self.VALID_DATA, "confidence": 1.5}
        with pytest.raises(ValidationError):
            ReferenceSolution(**data)

    def test_confidence_below_0_raises(self):
        data = {**self.VALID_DATA, "confidence": -0.1}
        with pytest.raises(ValidationError):
            ReferenceSolution(**data)

    def test_confidence_boundary_values(self):
        sol_zero = ReferenceSolution(**{**self.VALID_DATA, "confidence": 0.0})
        assert sol_zero.confidence == 0.0
        sol_one = ReferenceSolution(**{**self.VALID_DATA, "confidence": 1.0})
        assert sol_one.confidence == 1.0

    def test_structured_trace_optional(self):
        data = {k: v for k, v in self.VALID_DATA.items() if k != "structured_trace"}
        sol = ReferenceSolution(**data)
        assert sol.structured_trace is None

    def test_extra_fields_rejected(self):
        data = {**self.VALID_DATA, "extra_field": "should fail"}
        with pytest.raises(ValidationError):
            ReferenceSolution(**data)
