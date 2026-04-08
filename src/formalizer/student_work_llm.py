"""LLM prompt and retry loop for semantic-sketch student-work formalization."""
from __future__ import annotations

import json

from src.formalizer.student_work_builder import (
    _allowed_student_refs,
    _build_compact_student_draft,
    _build_student_work_from_sketch,
    _compare_with_heuristic_student_notes,
    _schema_validation_result,
)
from src.formalizer.student_work_validation import (
    _student_feedback_payload,
    _student_sanity_validation_result,
)
from src.llm import LLMClient
from src.models import (
    CanonicalReference,
    FormalizedProblem,
    GraphValidationIssue,
    GraphValidationResult,
    StudentStepAttempt,
    StudentWorkMode,
    StudentWorkState,
    TraceOperation,
)


def _build_llm_student_prompt(
    raw_answer: str,
    heuristic_state: StudentWorkState,
    problem: FormalizedProblem | None,
    feedback_issues: list[dict],
    attempt_index: int,
) -> tuple[str, str]:
    compact_draft = _build_compact_student_draft(heuristic_state, problem=problem)
    allowed_refs = _allowed_student_refs(problem)
    system_prompt = (
        "You are a student-work formalizer for math tutoring. Return only a compact semantic sketch JSON object, "
        "not the final StudentWorkState. Use the heuristic draft only as lightweight anchors. Keep everything "
        "strictly grounded in the student answer. Local code will compile your sketch into the final StudentWorkState "
        "and graph."
    )
    user_prompt = (
        f"Student answer:\n{raw_answer}\n\n"
        "Return one JSON object with only these top-level fields:\n"
        "{\n"
        '  "final_answer": {"value": null, "confidence": 0.0},\n'
        '  "mode": "final_answer_only|partial_trace|full_trace|unparseable",\n'
        '  "target": {"selected_ref": "...", "confidence": 0.0, "rationale": "..."},\n'
        '  "semantic_facts": [\n'
        '    {"fact_id": "...", "label": "...", "value": null, "grounding": "...", "confidence": 0.0, "notes": ["..."]}\n'
        "  ],\n"
        '  "trace_steps": [\n'
        '    {"surface_text": "...", "operation": "...", "input_values": [3.0, 5.0], "extracted_value": null, "referenced_ids": ["..."], "confidence": 0.0, "notes": ["..."]}\n'
        "  ],\n"
        '  "assumptions": ["..."],\n'
        '  "confidence": 0.0,\n'
        '  "notes": ["..."]\n'
        "}\n\n"
        f"Allowed mode values: {[mode.value for mode in StudentWorkMode]}\n"
        f"Allowed step operation values: {[operation.value for operation in TraceOperation]}\n"
        f"Allowed target.selected_ref and trace_steps.referenced_ids values: {allowed_refs}\n"
        "If trace_steps are present, list them in student order.\n\n"
        "Hard constraints:\n"
        "1. If the student explicitly states a final numeric answer such as 'Answer is 117', copy that number into final_answer.value.\n"
        "2. If the final numeric answer is not explicit, set final_answer.value to null instead of using a placeholder like 0 or 0.0.\n"
        "3. trace_steps.surface_text must be copied verbatim or nearly verbatim from the student answer; do not paraphrase it.\n"
        "4. target.selected_ref may contain only values from the allowed refs list.\n"
        "5. trace_steps.referenced_ids may contain values from the allowed refs list or ids declared in semantic_facts.\n"
        "6. Use semantic_facts for hidden numeric claims the student explicitly relies on, such as a combined multiplier or an intermediate constant.\n"
        "7. If the student's text does not support a field confidently, omit it or use null instead of guessing.\n"
        "8. Do not add steps that are not visible in the student's answer.\n"
        "9. Prefer a faithful step structure over collapsing everything into one giant step.\n"
        "10. Use only enum values exactly as listed above.\n\n"
        f"Attempt index: {attempt_index}\n\n"
        f"Structured feedback from the previous failed attempt:\n{json.dumps(feedback_issues, ensure_ascii=True)}\n\n"
        "Compact heuristic draft for reference only:\n"
        f"{json.dumps(compact_draft, ensure_ascii=True)}"
    )
    return system_prompt, user_prompt


def _student_missing_validation_result() -> GraphValidationResult:
    return GraphValidationResult(
        is_valid=False,
        issues=[
            GraphValidationIssue(
                code="student_missing_graph",
                message="Student work graph was not built from the semantic sketch",
            )
        ],
        operation_node_count=0,
        notes=["student_graph_missing"],
    )


def _llm_formalize_student_work(
    raw_answer: str,
    heuristic_state: StudentWorkState,
    problem: FormalizedProblem | None,
    reference: CanonicalReference | None,
    llm_client: LLMClient,
) -> StudentWorkState:
    feedback_issues: list[dict] = []
    last_validation_result = _student_missing_validation_result()

    for attempt_index in range(1, 4):
        system_prompt, user_prompt = _build_llm_student_prompt(
            raw_answer,
            heuristic_state,
            problem,
            feedback_issues,
            attempt_index,
        )
        payload = llm_client.generate_json(
            task_name="student_work_formalizer",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=10000,
        )
        payload["notes"] = list(payload.get("notes", [])) + [f"llm_student_parse_attempt:{attempt_index}"]

        try:
            refined = _build_student_work_from_sketch(
                raw_answer,
                heuristic_state,
                payload,
                problem=problem,
            )
        except (ValueError, TypeError) as exc:
            last_validation_result = _schema_validation_result(exc)
            feedback_issues = _student_feedback_payload(last_validation_result)
            continue

        last_validation_result = _student_sanity_validation_result(refined, problem=problem, reference=reference)
        if last_validation_result.is_valid:
            success_notes = list(refined.notes)
            success_notes.extend(_compare_with_heuristic_student_notes(heuristic_state, refined))
            if "llm_student_parse_used" not in success_notes:
                success_notes.append("llm_student_parse_used")
            success_notes.append("llm_student_semantic_sketch_used")
            if attempt_index > 1:
                success_notes.append(f"llm_student_parse_repaired_after:{attempt_index}")
            return refined.model_copy(update={"notes": success_notes})

        feedback_issues = _student_feedback_payload(last_validation_result)

    fallback_notes = list(heuristic_state.notes)
    fallback_notes.extend(f"student_graph_issue:{issue.code}" for issue in last_validation_result.issues)
    fallback_notes.append("llm_student_parse_failed_fallback")
    return heuristic_state.model_copy(update={"notes": fallback_notes})
