"""Qwen solver client: sends problems to a Qwen2.5-Math API and handles retries."""
import logging
import os
import time
import httpx
from typing import Optional

from src.models import SolverConfig, SolverResponse, SolverStatus

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_TEMPLATE = (
    "Solve the following math problem step by step:\n\n"
    "{problem}\n\n"
    "Show your work and end with #### <answer>"
)


class QwenSolverClient:
    """Client wrapper for Qwen2.5-Math via OpenAI-compatible API."""

    def __init__(self, config: Optional[SolverConfig] = None):
        self.config = config or SolverConfig()
        self._http_client: Optional[httpx.Client] = None

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None:
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            headers.update(self.config.extra_headers)

            self._http_client = httpx.Client(
                base_url=self.config.api_base,
                timeout=self.config.timeout_seconds,
                headers=headers,
            )
        return self._http_client

    def close(self):
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _build_payload(self, problem: str) -> dict:
        prompt = DEFAULT_PROMPT_TEMPLATE.format(problem=problem)
        return {
            "model": self.config.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

    def solve(self, problem: str) -> SolverResponse:
        """Send a problem to the solver and return a structured response.

        Implements bounded retries with exponential backoff.
        """
        start_time = time.monotonic()
        last_error: Optional[str] = None
        last_status = SolverStatus.API_ERROR

        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self.http_client.post(
                    "/chat/completions",
                    json=self._build_payload(problem),
                )

                if response.status_code == 429:
                    last_status = SolverStatus.RATE_LIMITED
                    last_error = "Rate limited (429)"
                    logger.warning("Attempt %d: rate limited", attempt)
                    self._backoff(attempt)
                    continue

                if response.status_code >= 400:
                    last_status = SolverStatus.API_ERROR
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning("Attempt %d: API error — %s", attempt, last_error)
                    self._backoff(attempt)
                    continue

                data = response.json()
                raw_text = data["choices"][0]["message"]["content"]

                elapsed_ms = (time.monotonic() - start_time) * 1000
                return SolverResponse(
                    raw_text=raw_text,
                    status=SolverStatus.SUCCESS,
                    model_name=self.config.model_name,
                    latency_ms=elapsed_ms,
                    attempt_count=attempt,
                )

            except httpx.TimeoutException:
                last_status = SolverStatus.TIMEOUT
                last_error = f"Timeout after {self.config.timeout_seconds}s"
                logger.warning("Attempt %d: timeout", attempt)
                self._backoff(attempt)

            except Exception as exc:
                last_status = SolverStatus.API_ERROR
                last_error = str(exc)
                logger.error("Attempt %d: unexpected error — %s", attempt, exc)
                self._backoff(attempt)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        return SolverResponse(
            raw_text=None,
            status=SolverStatus.MAX_RETRIES_EXCEEDED,
            model_name=self.config.model_name,
            latency_ms=elapsed_ms,
            attempt_count=self.config.max_retries,
            error_message=f"All {self.config.max_retries} retries exhausted. Last: {last_error}",
        )

    @staticmethod
    def _backoff(attempt: int):
        """Exponential backoff: 1s, 2s, 4s, ..."""
        delay = min(2 ** (attempt - 1), 8)
        time.sleep(delay)


def build_solver_config_from_env() -> SolverConfig:
    """Build a SolverConfig using OpenRouter-oriented environment variables."""
    extra_headers = {}
    referer = os.environ.get("OPENROUTER_HTTP_REFERER")
    app_name = os.environ.get("OPENROUTER_APP_NAME")
    if referer:
        extra_headers["HTTP-Referer"] = referer
    if app_name:
        extra_headers["X-Title"] = app_name

    return SolverConfig(
        model_name=os.environ.get("OPENROUTER_MODEL_ID", "qwen/qwen-2.5-7b-instruct"),
        api_base=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        timeout_seconds=float(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "30")),
        extra_headers=extra_headers,
    )
