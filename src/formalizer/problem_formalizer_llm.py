"""LLM prompt and retry loop for compact-skeleton problem formalization."""
from __future__ import annotations

import json

from pydantic import ValidationError

from src.formalizer.problem_formalizer_builder import (
    _build_compact_draft,
    _build_formalized_problem_from_skeleton,
    _merge_semantic_and_commitment_payloads,
)
from src.formalizer.problem_formalizer_validation import (
    _graph_feedback_payload,
    _missing_graph_validation_result,
    _schema_validation_result,
    validate_formalized_problem,
    validate_llm_semantic_state_payload,
    validate_llm_semantic_commitment_payload,
)
from src.llm import LLMClient
from src.llm import LLMGenerationError
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


def _build_llm_semantic_state_prompt(
    problem_text: str,
    heuristic_problem: FormalizedProblem,
    heuristic_evidence: dict,
    feedback_issues: list[dict],
    attempt_index: int,
) -> tuple[str, str]:
    compact_draft = _build_compact_draft(heuristic_problem, heuristic_evidence)
    system_prompt = (
        "You are a math problem formalizer. Return only a JSON semantic state artifact, not the final "
        "FormalizedProblem. Use the heuristic draft only as lightweight anchors and observed evidence hints, not "
        "as a closed-world inventory. Your job in this stage is structural parsing, not shortcut solving: infer "
        "the canonical entities, quantities, target, and declarative semantic structure of the problem. Do not "
        "return executable plan steps in this stage."
    )
    user_prompt = (
        f"Problem text:\n{problem_text}\n\n"
        "Return one JSON object with exactly these top-level fields:\n"
        "{\n"
        '  "entities": [\n'
        '    {"entity_id": "...", "surface_text": "...", "normalized_name": "...", "entity_type": "...", "aliases": ["..."], "grounding": "...", "notes": ["..."]}\n'
        "  ],\n"
        '  "quantities": [\n'
        '    {"quantity_id": "...", "surface_text": "...", "value": 0.0, "unit": "...", "entity_id": null, "semantic_role": "...", "is_target_candidate": true, "origin": "observed|latent|derived", "evidence_ref": null, "grounding": "...", "notes": ["..."]}\n'
        "  ],\n"
        '  "semantic_structure": [\n'
        '    {"structure_id": "...", "structure_type": "...", "input_quantity_ids": ["..."], "output_quantity_id": "...", "parameter_value": null, "parameter_quantity_id": null, "description": "...", "confidence": 0.0}\n'
        "  ],\n"
        '  "target": {"surface_text": "...", "normalized_question": "...", "target_variable": "...", "target_quantity_id": null, "entity_id": null, "unit": "...", "description": "...", "confidence": 0.0},\n'
        '  "relation": {"relation_type": "...", "operation_hint": "...", "source_quantity_ids": ["..."], "target_variable": "...", "rationale": "...", "confidence": 0.0},\n'
        '  "confidence": 0.0,\n'
        '  "notes": ["..."]\n'
        "}\n\n"
        f"Allowed quantity semantic_role values: {[role.value for role in QuantitySemanticRole]}\n"
        f"Allowed relation_type values: {[relation.value for relation in RelationType]}\n"
        f"Allowed operation_hint values: {[operation.value for operation in OperationType]}\n"
        "Hard constraints:\n"
        "1. Treat the draft as anchors, not as the full structure of the solution.\n"
        "2. entities is the canonical entity inventory for the problem. Use an empty list if no entities are needed.\n"
        "3. quantities is the canonical quantity inventory for the problem; do not assume the draft observed-quantity list is exhaustive.\n"
        "4. Use origin='observed' for quantities directly grounded in the problem text.\n"
        "5. Use origin='latent' or origin='derived' for quantities inferred from semantics rather than directly extracted from the draft.\n"
        "6. entity_id on quantities and target is optional; use null when no entity link is needed.\n"
        "7. evidence_ref is optional metadata only. Use it only when you are confident a quantity directly matches a draft observed quantity id; otherwise use null.\n"
        "8. semantic_structure is the primary declarative representation of hidden mathematical structure. Use it to express latent scaling, composition, comparison, partition, rate, or equivalence relations.\n"
        "9. Prefer declaring latent quantities plus semantic_structure over collapsing the whole problem into one shortcut relation.\n"
        "10. relation is only a coarse compatibility summary. Keep it lightweight, do not put executable expressions there, and use unknown when no simple coarse family fits.\n"
        "11. relation.target_variable should match target.target_variable when relation is present.\n"
        "12. Every quantity_id, entity_id, and structure_id must be stable and unique within the payload.\n"
        "13. target.target_variable must name the final answer quantity, not an intermediate.\n"
        "14. Do not return plan_steps, graph_target_node_id, graph_notes, or assumptions in this stage.\n"
        "15. quantity semantic_role must use the listed enum values. relation_type and operation_hint are compatibility metadata only; prefer the listed values there, and use unknown instead of inventing a new family when needed.\n"
        "16. When the text describes multiple local states, time slices, groups, or chained transformations, create one latent quantity per semantic state and one semantic_structure item per local relation.\n"
        "17. Do not algebraically collapse an explicit chain of local relations into a single combined factor or closed-form shortcut if the intermediate states are part of the problem semantics.\n"
        "18. If the final answer corresponds to one of the quantities you declare, set target.target_quantity_id to that quantity_id.\n"
        "19. This stage is not for numerically solving latent quantities. If a latent or derived quantity is needed structurally but its value is not directly observed, keep it unsolved and use value=0.0 as a placeholder.\n\n"
        f"Attempt index: {attempt_index}\n\n"
        f"Structured feedback from the previous failed attempt:\n{json.dumps(feedback_issues, ensure_ascii=True)}\n\n"
        "Anchor evidence pack for reference only:\n"
        f"{json.dumps(compact_draft, ensure_ascii=True)}"
    )
    return system_prompt, user_prompt


def _build_llm_commitment_prompt(
    problem_text: str,
    semantic_payload: dict,
    feedback_issues: list[dict],
    attempt_index: int,
) -> tuple[str, str]:
    observed_quantities: list[dict] = []
    latent_quantities: list[dict] = []
    latent_quantity_ids: set[str] = set()

    raw_quantities = semantic_payload.get("quantities")
    if isinstance(raw_quantities, list):
        for raw_quantity in raw_quantities:
            if not isinstance(raw_quantity, dict):
                continue
            quantity_id = str(raw_quantity.get("quantity_id", "")).strip()
            if not quantity_id:
                continue
            origin = str(raw_quantity.get("origin", "")).strip().lower()
            quantity_summary = {
                "quantity_id": quantity_id,
                "surface_text": raw_quantity.get("surface_text"),
            }
            if origin == "observed":
                quantity_summary["value"] = raw_quantity.get("value")
                observed_quantities.append(quantity_summary)
            else:
                latent_quantities.append(quantity_summary)
                latent_quantity_ids.add(quantity_id)

    compact_structures: list[dict] = []
    structure_output_ids: set[str] = set()
    raw_structures = semantic_payload.get("semantic_structure")
    if isinstance(raw_structures, list):
        for raw_structure in raw_structures:
            if not isinstance(raw_structure, dict):
                continue
            output_quantity_id = raw_structure.get("output_quantity_id")
            if isinstance(output_quantity_id, str) and output_quantity_id.strip():
                structure_output_ids.add(output_quantity_id.strip())
            compact_structures.append(
                {
                    "structure_id": raw_structure.get("structure_id"),
                    "structure_type": raw_structure.get("structure_type"),
                    "input_quantity_ids": raw_structure.get("input_quantity_ids", []),
                    "output_quantity_id": raw_structure.get("output_quantity_id"),
                    "parameter_value": raw_structure.get("parameter_value"),
                    "parameter_quantity_id": raw_structure.get("parameter_quantity_id"),
                }
            )

    target_block = semantic_payload.get("target") if isinstance(semantic_payload.get("target"), dict) else {}
    target_quantity_id = target_block.get("target_quantity_id")
    required_output_quantity_ids = sorted(
        {
            ref
            for ref in structure_output_ids.union({target_quantity_id} if isinstance(target_quantity_id, str) else set())
            if ref in latent_quantity_ids
        }
    )

    frozen_semantic_state = {
        "observed_quantities": observed_quantities,
        "latent_quantities": latent_quantities,
        "semantic_structure": compact_structures,
        "target": {
            "target_variable": target_block.get("target_variable"),
            "target_quantity_id": target_block.get("target_quantity_id"),
        },
        "required_output_quantity_ids": required_output_quantity_ids,
    }
    system_prompt = (
        "You are a math problem formalizer. Return only a JSON executable commitment artifact. The semantic state "
        "shown to you is already accepted and frozen. Do not redefine its meaning. Your job is to produce plan_steps "
        "that are complete, executable, and consistent with that semantic state. Local code will only type-check, "
        "materialize, and validate your artifact; it will not infer omitted reasoning steps for you."
    )
    user_prompt = (
        f"Problem text:\n{problem_text}\n\n"
        "Frozen execution core (must be preserved):\n"
        f"{json.dumps(frozen_semantic_state, ensure_ascii=True)}\n\n"
        "Return one JSON object with this exact shape:\n"
        "{\n"
        '  "plan_steps": [\n'
        '    {"step_id": "...", "step_index": 1, "operation": "...", "input_refs": ["..."], "output_ref": "...", "expression": "...", "label": "...", "output_unit": "...", "confidence": 0.0}\n'
        "  ]\n"
        "}\n\n"
        f"Allowed plan_steps operation values: {[operation.value for operation in TraceOperation]}\n\n"
        "Hard constraints:\n"
        "1. The final plan step must output either frozen target.target_variable or frozen target.target_quantity_id directly.\n"
        "2. plan_steps.expression must be executable RHS only; never include assignments like a = b.\n"
        "3. plan_steps.expression may use only arithmetic operators (+, -, *, /), parentheses, numeric literals, and max/min/abs.\n"
        "4. input_refs must explicitly list every non-constant symbol used by the expression.\n"
        "5. observed_quantities are the only numeric givens. latent_quantities are reusable only after you produce them in earlier plan_steps.\n"
        "6. Materialize frozen semantic_structure explicitly; do not ignore it and jump straight to a shortcut.\n"
        "7. Every ref in required_output_quantity_ids must appear as an output_ref before the final target step.\n"
        "8. plan_steps must be complete and executable on their own. Do not return prose, scaffolds, graph_notes, assumptions, or omitted later steps.\n"
        "9. Do not rename target.target_variable or any quantity ids from the frozen execution core.\n"
        "10. If you naturally end at frozen target.target_quantity_id, local code will bind that value to frozen target.target_variable deterministically; do not add prose to explain this.\n"
        "11. Use only the listed operation enum values.\n\n"
        f"Attempt index: {attempt_index}\n\n"
        f"Structured feedback from the previous failed attempt:\n{json.dumps(feedback_issues, ensure_ascii=True)}\n\n"
        "Return only the JSON object."
    )
    return system_prompt, user_prompt


def _llm_formalize_problem(
    problem_text: str,
    heuristic_problem: FormalizedProblem,
    heuristic_evidence: dict,
    llm_client: LLMClient,
) -> FormalizedProblem:
    semantic_feedback_issues: list[dict] = []
    commitment_feedback_issues: list[dict] = []
    last_validation_result = _missing_graph_validation_result()
    post_build_failure = False
    semantic_payload: dict | None = None

    for attempt_index in range(1, 4):
        system_prompt, user_prompt = _build_llm_semantic_state_prompt(
            problem_text,
            heuristic_problem,
            heuristic_evidence,
            semantic_feedback_issues,
            attempt_index,
        )
        try:
            semantic_payload = llm_client.generate_json(
                task_name="problem_formalizer_semantic_state",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=10000,
            )
        except LLMGenerationError as exc:
            last_validation_result = GraphValidationResult(
                is_valid=False,
                issues=[GraphValidationIssue(code="llm_generation_error", message=str(exc))],
                operation_node_count=0,
                notes=["semantic_state_generation_failed"],
            )
            semantic_feedback_issues = _graph_feedback_payload(last_validation_result)
            continue
        semantic_payload["problem_text"] = problem_text.strip()
        semantic_notes = list(semantic_payload.get("notes", []))
        semantic_notes.append(f"llm_semantic_state_attempt:{attempt_index}")
        semantic_payload["notes"] = semantic_notes

        last_validation_result = validate_llm_semantic_state_payload(semantic_payload, heuristic_problem)
        if not last_validation_result.is_valid:
            semantic_feedback_issues = _graph_feedback_payload(last_validation_result)
            continue

        break
    else:
        issue_notes = [f"graph_issue:{issue.code}" for issue in last_validation_result.issues]
        fallback_notes = list(heuristic_problem.notes) + issue_notes + ["llm_formalization_failed_fallback"]
        return heuristic_problem.model_copy(update={"notes": fallback_notes})

    assert semantic_payload is not None

    for attempt_index in range(1, 4):
        system_prompt, user_prompt = _build_llm_commitment_prompt(
            problem_text,
            semantic_payload,
            commitment_feedback_issues,
            attempt_index,
        )
        try:
            commitment_payload = llm_client.generate_json(
                task_name="problem_formalizer_executable_commitment",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=10000,
            )
        except LLMGenerationError as exc:
            last_validation_result = GraphValidationResult(
                is_valid=False,
                issues=[GraphValidationIssue(code="llm_generation_error", message=str(exc))],
                operation_node_count=0,
                notes=["executable_commitment_generation_failed"],
            )
            commitment_feedback_issues = _graph_feedback_payload(last_validation_result)
            continue
        commitment_payload["problem_text"] = problem_text.strip()
        commitment_notes = list(commitment_payload.get("notes", []))
        commitment_notes.append(f"llm_executable_commitment_attempt:{attempt_index}")
        commitment_payload["notes"] = commitment_notes

        last_validation_result = validate_llm_semantic_commitment_payload(commitment_payload, semantic_payload)
        if not last_validation_result.is_valid:
            commitment_feedback_issues = _graph_feedback_payload(last_validation_result)
            continue

        payload = _merge_semantic_and_commitment_payloads(semantic_payload, commitment_payload)
        try:
            refined = _build_formalized_problem_from_skeleton(problem_text, heuristic_problem, payload)
        except ValidationError as exc:
            last_validation_result = _schema_validation_result(exc)
            post_build_failure = True
            break
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
            post_build_failure = True
            break

        refined = validate_formalized_problem(refined)
        if refined.problem_graph is None:
            last_validation_result = _missing_graph_validation_result()
            post_build_failure = True
            break

        last_validation_result = validate_problem_graph(refined)
        if not last_validation_result.is_valid:
            post_build_failure = True
            break

        success_notes = list(refined.notes)
        success_notes.append("llm_formalization_used")
        success_notes.append("llm_semantic_state_used")
        success_notes.append("llm_executable_commitment_used")
        if attempt_index > 1:
            success_notes.append(f"llm_executable_commitment_repaired_after:{attempt_index}")
        return refined.model_copy(update={"notes": success_notes})

    issue_notes = [f"graph_issue:{issue.code}" for issue in last_validation_result.issues]
    fallback_notes = list(heuristic_problem.notes) + issue_notes
    if post_build_failure:
        fallback_notes.append("llm_formalization_post_build_failed")
    fallback_notes.append("llm_formalization_failed_fallback")
    return heuristic_problem.model_copy(update={"notes": fallback_notes})
