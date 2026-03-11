import pytest
import json
from unittest.mock import patch, MagicMock
import httpx

from src.models import SolverConfig, SolverStatus, SolverResponse
from src.solver.qwen_client import QwenSolverClient


def _mock_success_response(content: str = "Step 1: 5+3=8\n#### 8") -> httpx.Response:
    """Create a mock httpx.Response mimicking OpenAI API success."""
    data = {"choices": [{"message": {"content": content}}]}
    return httpx.Response(200, json=data)


def _mock_error_response(status_code: int = 500, text: str = "Internal Server Error") -> httpx.Response:
    return httpx.Response(status_code, text=text)


def _mock_rate_limit_response() -> httpx.Response:
    return httpx.Response(429, text="Rate limited")


class TestSolverConfig:
    def test_defaults(self):
        config = SolverConfig()
        assert config.model_name == "Qwen/Qwen2.5-Math-7B-Instruct"
        assert config.max_retries == 3
        assert config.timeout_seconds == 60.0
        assert config.temperature == 0.0

    def test_custom_config(self):
        config = SolverConfig(model_name="custom-model", max_retries=5, temperature=0.7)
        assert config.model_name == "custom-model"
        assert config.max_retries == 5

    def test_invalid_retries(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SolverConfig(max_retries=-1)

    def test_invalid_temperature(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SolverConfig(temperature=3.0)


class TestSolverResponse:
    def test_success_response(self):
        resp = SolverResponse(
            raw_text="Solution text",
            status=SolverStatus.SUCCESS,
            model_name="test-model",
            latency_ms=150.0,
            attempt_count=1,
        )
        assert resp.status == SolverStatus.SUCCESS
        assert resp.raw_text == "Solution text"

    def test_failure_response(self):
        resp = SolverResponse(
            raw_text=None,
            status=SolverStatus.MAX_RETRIES_EXCEEDED,
            model_name="test-model",
            latency_ms=5000.0,
            attempt_count=3,
            error_message="All retries failed",
        )
        assert resp.status == SolverStatus.MAX_RETRIES_EXCEEDED
        assert resp.raw_text is None


class TestQwenSolverClient:
    def _make_client(self, max_retries: int = 1) -> QwenSolverClient:
        config = SolverConfig(max_retries=max_retries, timeout_seconds=5.0)
        return QwenSolverClient(config=config)

    @patch.object(httpx.Client, "post")
    def test_successful_solve(self, mock_post):
        mock_post.return_value = _mock_success_response("Step 1: 5+3=8\n#### 8")
        client = self._make_client()

        result = client.solve("What is 5+3?")
        assert result.status == SolverStatus.SUCCESS
        assert result.raw_text == "Step 1: 5+3=8\n#### 8"
        assert result.attempt_count == 1
        assert result.latency_ms >= 0

    @patch("src.solver.qwen_client.QwenSolverClient._backoff")
    @patch.object(httpx.Client, "post")
    def test_api_error_then_success(self, mock_post, mock_backoff):
        mock_post.side_effect = [
            _mock_error_response(500),
            _mock_success_response("#### 42"),
        ]
        client = self._make_client(max_retries=2)

        result = client.solve("What is the answer?")
        assert result.status == SolverStatus.SUCCESS
        assert result.attempt_count == 2

    @patch("src.solver.qwen_client.QwenSolverClient._backoff")
    @patch.object(httpx.Client, "post")
    def test_all_retries_fail(self, mock_post, mock_backoff):
        mock_post.return_value = _mock_error_response(500)
        client = self._make_client(max_retries=3)

        result = client.solve("Problem?")
        assert result.status == SolverStatus.MAX_RETRIES_EXCEEDED
        assert result.raw_text is None
        assert result.attempt_count == 3
        assert "retries exhausted" in result.error_message

    @patch("src.solver.qwen_client.QwenSolverClient._backoff")
    @patch.object(httpx.Client, "post")
    def test_timeout_handling(self, mock_post, mock_backoff):
        mock_post.side_effect = httpx.TimeoutException("Connection timed out")
        client = self._make_client(max_retries=2)

        result = client.solve("Problem?")
        assert result.status == SolverStatus.MAX_RETRIES_EXCEEDED
        assert "Timeout" in result.error_message

    @patch("src.solver.qwen_client.QwenSolverClient._backoff")
    @patch.object(httpx.Client, "post")
    def test_rate_limit_handling(self, mock_post, mock_backoff):
        mock_post.side_effect = [
            _mock_rate_limit_response(),
            _mock_success_response("#### 10"),
        ]
        client = self._make_client(max_retries=2)

        result = client.solve("Problem?")
        assert result.status == SolverStatus.SUCCESS

    @patch.object(httpx.Client, "post")
    def test_solve_returns_model_name(self, mock_post):
        mock_post.return_value = _mock_success_response()
        config = SolverConfig(model_name="my-custom-model", max_retries=1)
        client = QwenSolverClient(config=config)

        result = client.solve("Problem?")
        assert result.model_name == "my-custom-model"
