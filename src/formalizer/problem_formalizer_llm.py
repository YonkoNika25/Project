"""LLM prompt and retry loop for compact-skeleton problem formalization."""
from __future__ import annotations

import json

from pydantic import ValidationError

from src.formalizer.problem_formalizer_builder import (
    _build_compact_draft,
    _build_formalized_problem_from_skeleton,
)
from src.formalizer.problem_formalizer_validation import (
    _graph_feedback_payload,
    _missing_graph_validation_result,
    _schema_validation_result,
    _semantic_sanity_validation_result,
    validate_formalized_problem,
)
from src.llm import LLMClient
from src.models import (
    FormalizedProblem,
    GraphValidationIssue,
    GraphValidationResult,
    OperationType,
    QuantitySemanticRole,
    RelationType,
    TraceOperation,
)
from src.runtime.graph_validator import validate_problem_graph


def _build_llm_graph_prompt(
    problem_text: str,
    heuristic_problem: FormalizedProblem,
    heuristic_evidence: dict,
    feedback_issues: list[dict],
    attempt_index: int,
) -> tuple[str, str]:
    compact_draft = _build_compact_draft(heuristic_problem, heuristic_evidence)
    system_prompt = (
        "You are a math problem formalizer. Return only a compact semantic sketch JSON object, not the final "
        "FormalizedProblem. Use the heuristic draft only as lightweight anchors. Your job is to infer the hidden "
        "mathematical structure and propose a clean executable plan sketch. Local code will compile your sketch "
        "into the final typed graph."
    )
    user_prompt = (
        f"Problem text:\n{problem_text}\n\n"
        "Return one JSON object with exactly these top-level fields:\n"
        "{\n"
        '  "quantity_annotations": [\n'
        '    {"quantity_id": "...", "semantic_role": "...", "unit": "...", "entity_id": "...", "is_target_candidate": true}\n'
        "  ],\n"
        '  "semantic_facts": [\n'
        '    {"fact_id": "total_multiplier", "label": "...", "value": 0.0, "unit": "...", "semantic_role": "...", "grounding": "...", "notes": ["..."]}\n'
        "  ],\n"
        '  "target": {"surface_text": "...", "normalized_question": "...", "target_variable": "...", "target_quantity_id": "...", "entity_id": "...", "unit": "...", "description": "...", "confidence": 0.0},\n'
        '  "relation": {"relation_type": "...", "operation_hint": "...", "source_quantity_ids": ["..."], "target_variable": "...", "expression": "...", "rationale": "...", "confidence": 0.0},\n'
        '  "plan_steps": [\n'
        '    {"step_id": "...", "step_index": 1, "operation": "...", "input_refs": ["..."], "output_ref": "...", "expression": "...", "label": "...", "output_unit": "...", "confidence": 0.0}\n'
        "  ],\n"
        '  "graph_target_node_id": "...",\n'
        '  "graph_confidence": 0.0,\n'
        '  "graph_notes": ["..."],\n'
        '  "assumptions": ["..."],\n'
        '  "confidence": 0.0,\n'
        '  "notes": ["..."]\n'
        "}\n\n"
        f"Allowed quantity semantic_role values: {[role.value for role in QuantitySemanticRole]}\n"
        f"Allowed relation_type values: {[relation.value for relation in RelationType]}\n"
        f"Allowed operation_hint values: {[operation.value for operation in OperationType]}\n"
        f"Allowed plan_steps operation values: {[operation.value for operation in TraceOperation]}\n\n"
        "Hard constraints:\n"
        "1. Treat the draft as anchors, not as the full structure of the solution.\n"
        "2. If the problem needs hidden numeric facts, place them in semantic_facts.\n"
        "3. Do not invent new quantity ids like quantity_2 or quantity_3 unless they already exist in the draft.\n"
        "4. plan_steps.expression must be executable RHS only; never include assignments like a = b.\n"
        "5. graph_target_node_id must match target.target_variable or the heuristic target variable.\n"
        "6. The final target must be reachable from the plan_steps sequence.\n"
        "7. Prefer a faithful intermediate structure over jumping straight to the final answer.\n"
        "8. Use only enum values exactly as listed above.\n\n"
        f"Attempt index: {attempt_index}\n\n"
        f"Structured feedback from the previous failed attempt:\n{json.dumps(feedback_issues, ensure_ascii=True)}\n\n"
        "Anchor evidence pack and heuristic projection for reference only:\n"
        f"{json.dumps(compact_draft, ensure_ascii=True)}"
    )
    return system_prompt, user_prompt


def _llm_formalize_problem(
    problem_text: str,
    heuristic_problem: FormalizedProblem,
    heuristic_evidence: dict,
    llm_client: LLMClient,
) -> FormalizedProblem:
    feedback_issues: list[dict] = []
    last_validation_result = _missing_graph_validation_result()

    for attempt_index in range(1, 4):
        system_prompt, user_prompt = _build_llm_graph_prompt(
            problem_text,
            heuristic_problem,
            heuristic_evidence,
            feedback_issues,
            attempt_index,
        )
        payload = llm_client.generate_json(
            task_name="problem_formalizer",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=10000,
        )
        payload["problem_text"] = problem_text.strip()
        notes = list(payload.get("notes", []))
        notes.append(f"llm_formalization_attempt:{attempt_index}")
        payload["notes"] = notes

        try:
            refined = _build_formalized_problem_from_skeleton(problem_text, heuristic_problem, payload)
        except ValidationError as exc:
            last_validation_result = _schema_validation_result(exc)
            feedback_issues = _graph_feedback_payload(last_validation_result)
            continue
        except (ValueError, TypeError) as exc:
            last_validation_result = GraphValidationResult(
                is_valid=False,
                issues=[
                    GraphValidationIssue(
                        code="skeleton_build_error",
                        message=str(exc),
                    )
                ],
                operation_node_count=0,
                notes=["skeleton_build_failed"],
            )
            feedback_issues = _graph_feedback_payload(last_validation_result)
            continue

        refined = validate_formalized_problem(refined)
        if refined.problem_graph is None:
            last_validation_result = _missing_graph_validation_result()
            feedback_issues = _graph_feedback_payload(last_validation_result)
            continue

        last_validation_result = validate_problem_graph(refined)
        if last_validation_result.is_valid:
            semantic_validation = _semantic_sanity_validation_result(refined)
            if not semantic_validation.is_valid:
                last_validation_result = semantic_validation
                feedback_issues = _graph_feedback_payload(last_validation_result)
                continue
            success_notes = list(refined.notes)
            success_notes.append("llm_formalization_used")
            success_notes.append("llm_semantic_sketch_used")
            if attempt_index > 1:
                success_notes.append(f"llm_formalization_repaired_after:{attempt_index}")
            return refined.model_copy(update={"notes": success_notes})

        feedback_issues = _graph_feedback_payload(last_validation_result)

    issue_notes = [f"graph_issue:{issue.code}" for issue in last_validation_result.issues]
    fallback_notes = list(heuristic_problem.notes) + issue_notes + ["llm_formalization_failed_fallback"]
    return heuristic_problem.model_copy(update={"notes": fallback_notes})
