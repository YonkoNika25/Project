import pytest
from pydantic import ValidationError
from src.models import HintLevel, HintResult, DiagnosisLabel


class TestHintSchemas:
    def test_valid_hint_result(self):
        result = HintResult(
            hint_level=HintLevel.CONCEPTUAL,
            hint_text="Think about the total number of apples.",
            generated_status="success",
            diagnosis_label_used=DiagnosisLabel.ARITHMETIC_ERROR,
            fallback_used=False
        )
        assert result.hint_level == HintLevel.CONCEPTUAL
        assert result.hint_text == "Think about the total number of apples."
        assert result.generated_status == "success"

    def test_invalid_hint_level(self):
        with pytest.raises(ValidationError):
            HintResult(
                hint_level="invalid_level",
                hint_text="Test",
                generated_status="success",
                diagnosis_label_used=DiagnosisLabel.ARITHMETIC_ERROR
            )

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            HintResult(
                hint_level=HintLevel.NEXT_STEP,
                hint_text="Test",
                generated_status="success",
                diagnosis_label_used=DiagnosisLabel.ARITHMETIC_ERROR,
                extra_field="nope"
            )
