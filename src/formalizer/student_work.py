"""Student work formalization entrypoint."""
from __future__ import annotations

from src.formalizer.student_work_builder import _heuristic_formalize_student_work
from src.formalizer.student_work_llm import _llm_formalize_student_work
from src.llm import LLMClient, LLMGenerationError
from src.models import CanonicalReference, FormalizedProblem, StudentWorkState


def formalize_student_work(
    raw_answer: str,
    problem: FormalizedProblem | None = None,
    reference: CanonicalReference | None = None,
    llm_client: LLMClient | None = None,
) -> StudentWorkState:
    """Convert raw student work into a structured `StudentWorkState`."""
    # Build deterministic anchors first (final answer guess, parsed steps, student graph).
    heuristic_state = _heuristic_formalize_student_work(raw_answer, problem=problem, reference=reference)
    if llm_client is None:
        return heuristic_state

    try:
        # LLM refines by returning a semantic sketch; local code compiles and validates it.
        return _llm_formalize_student_work(
            raw_answer,
            heuristic_state,
            problem,
            reference,
            llm_client,
        )
    except (LLMGenerationError, ValueError, TypeError):
        # Never fail hard in production flow: preserve heuristic state with fallback note.
        notes = list(heuristic_state.notes)
        notes.append("llm_student_parse_failed_fallback")
        return heuristic_state.model_copy(update={"notes": notes})
