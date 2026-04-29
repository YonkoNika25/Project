"""LLM prompts and retry loops for student-work formalization."""
from __future__ import annotations

import json

from pydantic import ValidationError

from src.formalizer.student_work_builder import (
    _allowed_student_refs,
    _build_compact_student_context,
    _build_compact_student_draft,
    _build_student_work_from_artifacts,
    _compare_with_heuristic_student_notes,
    _known_problem_ref_values,
    _schema_validation_result,
)
from src.formalizer.student_work_validation import (
    _student_feedback_payload,
    _student_sanity_validation_result,
    validate_llm_student_semantic_state_payload,
    validate_llm_student_trace_commitment_payload,
)
from src.llm import LLMClient
from src.models import (
    CanonicalReference,
    FormalizedProblem,
    GraphValidationIssue,
    GraphValidationResult,
    StudentWorkMode,
    StudentWorkState,
    TraceOperation,
)


def _build_llm_student_semantic_prompt(
    raw_answer: str,
    heuristic_state: StudentWorkState,
    problem: FormalizedProblem | None,
    feedback_issues: list[dict],
    attempt_index: int,
) -> tuple[str, str]:
    compact_draft = _build_compact_student_draft(heuristic_state, problem=problem)
    canonical_context = _build_compact_student_context(problem)
    allowed_refs = _allowed_student_refs(problem)
    system_prompt = (
        "You are a student-work formalizer for math tutoring. Return only a JSON semantic state artifact, "
        "not the final StudentWorkState. Use the heuristic draft only as lightweight surface anchors, not as "
        "a semantic authority. Use the compact problem context only to map the student's answer onto known "
        "problem refs; do not infer hidden canonical solution structure."
    )
    user_prompt = (
        f"Student answer:\n{raw_answer}\n\n"
        "Return one JSON object with only these top-level fields:\n"
        "{\n"
        '  "final_answer": {"value": null, "confidence": 0.0},\n'
        '  "mode": "final_answer_only|partial_trace|full_trace|unparseable",\n'
        '  "target": {"selected_ref": null, "confidence": 0.0, "rationale": "..."},\n'
        '  "semantic_facts": [\n'
        '    {"fact_id": "...", "label": "...", "value": null, "grounding": "...", "confidence": 0.0, "notes": ["..."]}\n'
        "  ],\n"
        '  "confidence": 0.0,\n'
        '  "notes": ["..."]\n'
        "}\n\n"
        f"Allowed mode values: {[mode.value for mode in StudentWorkMode]}\n"
        f"Allowed problem refs for target.selected_ref: {allowed_refs}\n\n"
        "Hard constraints:\n"
        "1. If the student explicitly states a final numeric answer, or the final visible student step itself states a numeric result, copy only that visible number into final_answer.value.\n"
        "2. If the final numeric answer is not visibly stated in the student answer, set final_answer.value to null instead of guessing.\n"
        "3. mode must describe the observable structure of the student answer only. Preserve visible student process when it is clearly present; use final_answer_only only when the answer truly contains no usable step structure.\n"
        "4. target.selected_ref may be null, or one of the allowed problem refs when that ref is the best semantic match to the student's answer under the problem context.\n"
        "5. Use semantic_facts sparingly for grounded claims that help disambiguate the student's intent, target, or key visible commitments. Do not mirror every visible line as a separate semantic_fact if the trace stage can carry that process.\n"
        "6. Do not return trace_steps or assumptions in this stage.\n"
        "7. Do not add hidden reasoning from an external solution into semantic_facts or notes.\n"
        "8. Each semantic_fact.grounding should quote or closely reuse a short supporting phrase or line from the student answer. Avoid generic paraphrases like 'Student states...' without including the supporting text span.\n"
        "9. If the student's text does not support a field confidently, omit it or use null instead of guessing.\n"
        "10. Use only enum values exactly as listed above.\n\n"
        f"Attempt index: {attempt_index}\n\n"
        f"Structured feedback from the previous failed attempt:\n{json.dumps(feedback_issues, ensure_ascii=True)}\n\n"
        "Compact problem context:\n"
        f"{json.dumps(canonical_context, ensure_ascii=True)}\n\n"
        "Compact heuristic draft:\n"
        f"{json.dumps(compact_draft, ensure_ascii=True)}"
    )
    return system_prompt, user_prompt


def _build_llm_student_commitment_prompt(
    raw_answer: str,
    semantic_payload: dict,
    problem: FormalizedProblem | None,
    feedback_issues: list[dict],
    attempt_index: int,
) -> tuple[str, str]:
    canonical_context = _build_compact_student_context(problem)
    allowed_refs = _allowed_student_refs(problem)
    system_prompt = (
        "You are a student-work formalizer for math tutoring. Return only a JSON trace commitment artifact, "
        "not the final StudentWorkState. The semantic state is frozen. Your job is to encode only the visible "
        "student trace in student order. Do not add hidden reasoning or external solution steps."
    )
    user_prompt = (
        f"Student answer:\n{raw_answer}\n\n"
        f"Frozen semantic state:\n{json.dumps(semantic_payload, ensure_ascii=True)}\n\n"
        "Return one JSON object with only these top-level fields:\n"
        "{\n"
        '  "trace_steps": [\n'
        '    {"surface_text": "...", "operation": "...", "input_values": [3.0, 5.0], "extracted_value": null, "referenced_ids": ["..."], "confidence": 0.0, "notes": ["..."]}\n'
        "  ],\n"
        '  "assumptions": ["..."],\n'
        '  "confidence": 0.0,\n'
        '  "notes": ["..."]\n'
        "}\n\n"
        f"Allowed step operation values: {[operation.value for operation in TraceOperation]}\n"
        f"Allowed problem refs for trace_steps.referenced_ids: {allowed_refs}\n\n"
        "Hard constraints:\n"
        "1. Do not redefine final_answer, mode, target, or semantic_facts.\n"
        "2. If frozen mode is final_answer_only or unparseable, return an empty trace_steps list.\n"
        "3. If frozen mode is partial_trace or full_trace, return trace_steps in student order.\n"
        "4. Every trace step must include surface_text copied verbatim or nearly verbatim from the student answer.\n"
        "5. trace_steps.referenced_ids may use only allowed problem refs or fact_id values declared in the frozen semantic state.\n"
        "6. trace_steps.input_values and extracted_value must be numerically supported by the step text or the refs used by that step. Include input_values only when those numbers are explicitly visible in that same step or directly licensed by the referenced ids; otherwise leave input_values empty instead of inventing hidden operands. For fractions or percents, prefer the same form the student wrote unless the same step directly licenses the normalized value.\n"
        "7. If frozen final_answer.value is present and frozen target.selected_ref is null, at least one visible trace step must carry extracted_value equal to that final answer value. Use an already-visible step such as 'x = 34' or 'Answer is 34' if the student explicitly wrote it; do not invent a new step.\n"
        "8. Do not add steps that are not visible in the student answer.\n"
        "9. Do not invent missing steps, and do not omit surface_text for a returned step.\n"
        "10. Use only enum values exactly as listed above.\n\n"
        f"Attempt index: {attempt_index}\n\n"
        f"Structured feedback from the previous failed attempt:\n{json.dumps(feedback_issues, ensure_ascii=True)}\n\n"
        "Compact problem context:\n"
        f"{json.dumps(canonical_context, ensure_ascii=True)}\n\n"
        "Return only the JSON object."
    )
    return system_prompt, user_prompt


def _student_missing_validation_result() -> GraphValidationResult:
    return GraphValidationResult(
        is_valid=False,
        issues=[
            GraphValidationIssue(
                code="student_missing_graph",
                message="Student work graph was not built from the semantic artifact",
            )
        ],
        operation_node_count=0,
        notes=["student_graph_missing"],
    )


def _student_build_failure_result(message: str) -> GraphValidationResult:
    return GraphValidationResult(
        is_valid=False,
        issues=[
            GraphValidationIssue(
                code="student_build_error",
                message=message,
            )
        ],
        operation_node_count=0,
        notes=["student_build_failed"],
    )


def _llm_formalize_student_work(
    raw_answer: str,
    heuristic_state: StudentWorkState,
    problem: FormalizedProblem | None,
    reference: CanonicalReference | None,
    llm_client: LLMClient,
) -> StudentWorkState:
    allowed_refs = set(_allowed_student_refs(problem))
    semantic_feedback_issues: list[dict] = []
    commitment_feedback_issues: list[dict] = []
    last_validation_result = _student_missing_validation_result()
    semantic_payload: dict | None = None

    for attempt_index in range(1, 4):
        system_prompt, user_prompt = _build_llm_student_semantic_prompt(
            raw_answer,
            heuristic_state,
            problem,
            semantic_feedback_issues,
            attempt_index,
        )
        payload = llm_client.generate_json(
            task_name="student_work_semantic_state",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=10000,
        )
        payload["notes"] = list(payload.get("notes", [])) + [f"llm_student_semantic_state_attempt:{attempt_index}"]

        last_validation_result = validate_llm_student_semantic_state_payload(
            payload,
            allowed_refs=allowed_refs,
            raw_answer=raw_answer,
            problem=problem,
        )
        if last_validation_result.is_valid:
            semantic_payload = payload
            break

        semantic_feedback_issues = _student_feedback_payload(last_validation_result)

    if semantic_payload is None:
        fallback_notes = list(heuristic_state.notes)
        fallback_notes.extend(f"student_graph_issue:{issue.code}" for issue in last_validation_result.issues)
        fallback_notes.append("llm_student_semantic_state_failed_fallback")
        return heuristic_state.model_copy(update={"notes": fallback_notes})

    commitment_payload: dict | None = None
    for attempt_index in range(1, 4):
        system_prompt, user_prompt = _build_llm_student_commitment_prompt(
            raw_answer,
            semantic_payload,
            problem,
            commitment_feedback_issues,
            attempt_index,
        )
        payload = llm_client.generate_json(
            task_name="student_work_trace_commitment",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=10000,
        )
        payload["notes"] = list(payload.get("notes", [])) + [f"llm_student_trace_commitment_attempt:{attempt_index}"]

        last_validation_result = validate_llm_student_trace_commitment_payload(
            payload,
            raw_answer=raw_answer,
            semantic_payload=semantic_payload,
            allowed_refs=allowed_refs,
            problem_ref_values=_known_problem_ref_values(problem),
        )
        if last_validation_result.is_valid:
            commitment_payload = payload
            break

        commitment_feedback_issues = _student_feedback_payload(last_validation_result)

    if commitment_payload is None:
        fallback_notes = list(heuristic_state.notes)
        fallback_notes.extend(f"student_graph_issue:{issue.code}" for issue in last_validation_result.issues)
        fallback_notes.append("llm_student_trace_commitment_failed_fallback")
        return heuristic_state.model_copy(update={"notes": fallback_notes})

    try:
        refined = _build_student_work_from_artifacts(
            raw_answer,
            heuristic_state,
            semantic_payload,
            commitment_payload,
            problem=problem,
        )
    except ValueError as exc:
        last_validation_result = _student_build_failure_result(str(exc))
    except TypeError as exc:
        last_validation_result = _student_build_failure_result(str(exc))
    except ValidationError as exc:
        last_validation_result = _schema_validation_result(exc)
    else:
        last_validation_result = _student_sanity_validation_result(refined, problem=problem)
        if last_validation_result.is_valid:
            success_notes = list(refined.notes)
            success_notes.extend(_compare_with_heuristic_student_notes(heuristic_state, refined))
            if "llm_student_parse_used" not in success_notes:
                success_notes.append("llm_student_parse_used")
            success_notes.append("llm_student_semantic_state_used")
            success_notes.append("llm_student_trace_commitment_used")
            return refined.model_copy(update={"notes": success_notes})

    fallback_notes = list(heuristic_state.notes)
    fallback_notes.extend(f"student_graph_issue:{issue.code}" for issue in last_validation_result.issues)
    fallback_notes.append("llm_student_post_build_failed")
    return heuristic_state.model_copy(update={"notes": fallback_notes})
