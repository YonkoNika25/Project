"""Public entrypoint for problem formalization."""
from __future__ import annotations

from src.formalizer.problem_formalizer_builder import _heuristic_formalize_problem
from src.formalizer.problem_formalizer_llm import _llm_formalize_problem
from src.formalizer.problem_formalizer_validation import validate_formalized_problem
from src.llm import LLMClient, LLMGenerationError
from src.models import FormalizedProblem


def formalize_problem(
    problem_text: str,
    llm_client: LLMClient | None = None,
) -> FormalizedProblem:
    """Build a structured problem representation from raw text."""
    # Always produce a deterministic baseline first. This object is both:
    # 1) the return value when no LLM is provided, and
    # 2) the fallback when LLM refinement fails.
    heuristic_problem, heuristic_evidence = _heuristic_formalize_problem(problem_text)
    if llm_client is None:
        return heuristic_problem

    try:
        # LLM returns a compact semantic sketch; local code compiles/validates it.
        return _llm_formalize_problem(problem_text, heuristic_problem, heuristic_evidence, llm_client)
    except (LLMGenerationError, ValueError, TypeError):
        # Keep failures non-fatal for the pipeline by returning the heuristic artifact.
        notes = list(heuristic_problem.notes)
        notes.append("llm_formalization_failed_fallback")
        return heuristic_problem.model_copy(update={"notes": notes})


__all__ = ["formalize_problem", "validate_formalized_problem"]
