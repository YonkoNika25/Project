from pydantic import ValidationError
import pytest

from src.models import (
    DiagnosisLabel,
    ErrorLocalization,
    OperationType,
    QuantityFact,
    SymbolicState,
    VerificationResult,
    VerificationStatus,
)


def test_quantity_fact_valid():
    fact = QuantityFact(surface_form="1,234", value=1234.0)
    assert fact.value == 1234.0


def test_symbolic_state_defaults():
    state = SymbolicState()
    assert state.quantities == []
    assert state.expected_operation == OperationType.UNKNOWN


def test_verification_result_valid():
    result = VerificationResult(
        status=VerificationStatus.CONFLICT,
        predicted_label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
        localization_hint=ErrorLocalization.INTERMEDIATE_STEP,
        confidence=0.9,
    )
    assert result.status == VerificationStatus.CONFLICT


def test_verification_result_confidence_range():
    with pytest.raises(ValidationError):
        VerificationResult(status=VerificationStatus.VERIFIED, confidence=1.2)
