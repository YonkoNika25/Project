"""Reference solution parser: converts raw solver output into validated ReferenceSolution."""
import logging
from typing import Optional, Union
from dataclasses import dataclass
from enum import Enum

from src.models import ReferenceSolution, SolverResponse, SolverStatus
from src.dataset.answer_parser import parse_gsm8k_answer

logger = logging.getLogger(__name__)


class ParseStatus(str, Enum):
    SUCCESS = "success"
    NO_ANSWER_FOUND = "no_answer_found"
    SOLVER_FAILED = "solver_failed"


@dataclass
class ParseResult:
    """Result of parsing a solver response into a ReferenceSolution."""
    status: ParseStatus
    reference: Optional[ReferenceSolution] = None
    error_message: Optional[str] = None


def parse_solver_response(
    solver_response: SolverResponse,
    schema_version: str = "1.0",
) -> ParseResult:
    """Parse a SolverResponse into a validated ReferenceSolution.

    Args:
        solver_response: The raw response from QwenSolverClient.
        schema_version: Version tag for the schema.

    Returns:
        ParseResult with status and optional ReferenceSolution.
    """
    if solver_response.status != SolverStatus.SUCCESS or not solver_response.raw_text:
        return ParseResult(
            status=ParseStatus.SOLVER_FAILED,
            error_message=f"Solver did not succeed: {solver_response.status.value}",
        )

    raw_text = solver_response.raw_text
    normalized = raw_text.strip()
    if normalized.startswith("Error calling LLM:") or normalized.startswith("Error: OPENROUTER_API_KEY is missing."):
        return ParseResult(
            status=ParseStatus.SOLVER_FAILED,
            error_message=normalized,
        )

    gold_value, parsed_ok = parse_gsm8k_answer(raw_text)

    if not parsed_ok or gold_value is None:
        return ParseResult(
            status=ParseStatus.NO_ANSWER_FOUND,
            error_message="Could not extract #### <number> from solver output",
        )

    confidence = 1.0 if parsed_ok else 0.5

    try:
        ref = ReferenceSolution(
            final_answer=gold_value,
            solution_text=raw_text,
            confidence=confidence,
            schema_version=schema_version,
            source=solver_response.model_name,
        )
        return ParseResult(status=ParseStatus.SUCCESS, reference=ref)
    except Exception as exc:
        return ParseResult(
            status=ParseStatus.NO_ANSWER_FOUND,
            error_message=f"Schema validation failed: {exc}",
        )


def get_reference_solution(
    client,  # QwenSolverClient
    problem: str,
    schema_version: str = "1.0",
) -> ParseResult:
    """High-level pipeline: solve a problem and parse the result.

    Args:
        client: A QwenSolverClient instance.
        problem: The math problem text.
        schema_version: Version tag for the schema.

    Returns:
        ParseResult with status and optional ReferenceSolution.
    """
    solver_response = client.solve(problem)
    return parse_solver_response(solver_response, schema_version=schema_version)
