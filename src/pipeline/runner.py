"""End-to-end tutoring pipeline runner."""
from __future__ import annotations

from src.diagnosis import build_diagnosis
from src.evidence import build_diagnosis_context, build_diagnosis_evidence
from src.formalizer import formalize_problem, formalize_student_work
from src.hint import build_hint_result
from src.llm import LLMClient, build_default_llm_client
from src.models import HintMode, TutoringResult
from src.pedagogy import build_pedagogy_artifacts
from src.runtime import build_canonical_reference


def run_tutoring_pipeline(
    problem_text: str,
    student_answer: str,
    hint_mode: HintMode = HintMode.NORMAL,
    llm_client: LLMClient | None = None,
    use_llm: bool = True,
) -> TutoringResult:
    """Run the full deterministic tutoring pipeline."""
    active_llm_client = llm_client
    if active_llm_client is None and use_llm:
        active_llm_client = build_default_llm_client()

    problem = formalize_problem(problem_text, llm_client=active_llm_client)
    reference = build_canonical_reference(problem)
    student_work = formalize_student_work(
        student_answer,
        problem=problem,
        reference=reference,
        llm_client=active_llm_client,
    )
    evidence = build_diagnosis_evidence(problem, reference, student_work)
    diagnosis_context = build_diagnosis_context(problem, reference, student_work, evidence)
    diagnosis_state, diagnosis = build_diagnosis(
        evidence,
        context=diagnosis_context,
        llm_client=active_llm_client,
    )
    pedagogy_state, hint_strategy, hint_plan = build_pedagogy_artifacts(
        problem,
        reference,
        diagnosis,
        diagnosis_state,
        llm_client=active_llm_client,
    )
    hint_result = build_hint_result(
        problem,
        reference,
        diagnosis,
        hint_plan,
        strategy=hint_strategy,
        hint_mode=hint_mode,
        llm_client=active_llm_client,
    )

    return TutoringResult(
        problem=problem,
        reference=reference,
        student_work=student_work,
        evidence=evidence,
        diagnosis=diagnosis,
        diagnosis_state=diagnosis_state,
        pedagogy_state=pedagogy_state,
        hint_plan=hint_plan,
        hint_strategy=hint_strategy,
        hint_result=hint_result,
    )
