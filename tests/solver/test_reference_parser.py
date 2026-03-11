import pytest
from unittest.mock import MagicMock

from src.models import SolverResponse, SolverStatus, ReferenceSolution
from src.solver.reference_parser import (
    parse_solver_response,
    get_reference_solution,
    ParseResult,
    ParseStatus,
)


def _make_solver_response(
    raw_text: str = "Step 1: 5+3=8\n#### 8",
    status: SolverStatus = SolverStatus.SUCCESS,
    model_name: str = "test-model",
) -> SolverResponse:
    return SolverResponse(
        raw_text=raw_text,
        status=status,
        model_name=model_name,
        latency_ms=100.0,
        attempt_count=1,
    )


class TestParseSolverResponse:
    def test_success(self):
        resp = _make_solver_response("Let me solve this.\n5+3=8\n#### 8")
        result = parse_solver_response(resp)
        assert result.status == ParseStatus.SUCCESS
        assert result.reference is not None
        assert result.reference.final_answer == 8.0
        assert result.reference.confidence == 1.0
        assert result.reference.source == "test-model"
        assert result.reference.schema_version == "1.0"

    def test_no_answer_pattern(self):
        resp = _make_solver_response("I think the answer is eight")
        result = parse_solver_response(resp)
        assert result.status == ParseStatus.NO_ANSWER_FOUND
        assert result.reference is None
        assert result.error_message is not None

    def test_solver_failed(self):
        resp = SolverResponse(
            raw_text=None,
            status=SolverStatus.MAX_RETRIES_EXCEEDED,
            model_name="test-model",
            latency_ms=5000.0,
            attempt_count=3,
            error_message="All retries failed",
        )
        result = parse_solver_response(resp)
        assert result.status == ParseStatus.SOLVER_FAILED

    def test_solver_api_error(self):
        resp = SolverResponse(
            raw_text=None,
            status=SolverStatus.API_ERROR,
            model_name="test-model",
            latency_ms=200.0,
            attempt_count=1,
            error_message="HTTP 500",
        )
        result = parse_solver_response(resp)
        assert result.status == ParseStatus.SOLVER_FAILED

    def test_reference_conforms_to_schema(self):
        resp = _make_solver_response("Work: 7*6=42\n#### 42")
        result = parse_solver_response(resp)
        assert isinstance(result.reference, ReferenceSolution)
        assert result.reference.final_answer == 42.0

    def test_negative_answer(self):
        resp = _make_solver_response("Result is negative.\n#### -15")
        result = parse_solver_response(resp)
        assert result.status == ParseStatus.SUCCESS
        assert result.reference.final_answer == -15.0

    def test_decimal_answer(self):
        resp = _make_solver_response("Pi approx.\n#### 3.14")
        result = parse_solver_response(resp)
        assert result.status == ParseStatus.SUCCESS
        assert result.reference.final_answer == 3.14

    def test_custom_schema_version(self):
        resp = _make_solver_response("#### 10")
        result = parse_solver_response(resp, schema_version="2.0")
        assert result.reference.schema_version == "2.0"


class TestGetReferenceSolution:
    def test_pipeline_success(self):
        mock_client = MagicMock()
        mock_client.solve.return_value = _make_solver_response("#### 25")

        result = get_reference_solution(mock_client, "What is 5*5?")
        assert result.status == ParseStatus.SUCCESS
        assert result.reference.final_answer == 25.0
        mock_client.solve.assert_called_once_with("What is 5*5?")

    def test_pipeline_solver_failure(self):
        mock_client = MagicMock()
        mock_client.solve.return_value = SolverResponse(
            raw_text=None,
            status=SolverStatus.TIMEOUT,
            model_name="test",
            latency_ms=60000.0,
            attempt_count=3,
            error_message="Timeout",
        )

        result = get_reference_solution(mock_client, "Problem?")
        assert result.status == ParseStatus.SOLVER_FAILED
        assert result.reference is None

    def test_pipeline_parse_failure(self):
        mock_client = MagicMock()
        mock_client.solve.return_value = _make_solver_response("No answer here")

        result = get_reference_solution(mock_client, "Problem?")
        assert result.status == ParseStatus.NO_ANSWER_FOUND
