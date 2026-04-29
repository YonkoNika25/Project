"""Validation, repair, and acceptance policy helpers for problem formalization."""
from __future__ import annotations

import ast

from pydantic import ValidationError

from src.models import (
    FormalizedProblem,
    GraphValidationIssue,
    GraphValidationResult,
    OperationType,
    ProblemEntity,
    ProblemGraphEdgeType,
    ProblemGraphNodeType,
    ProvenanceSource,
    QuantityAnnotation,
    QuantitySemanticRole,
    RelationCandidate,
    RelationType,
    TargetSpec,
)

from src.formalizer.problem_formalizer_extractors import _dedupe_quantities


def _sanitize_quantity_update(quantity_update: dict) -> tuple[dict, str | None]:
    sanitized = dict(quantity_update)
    invalid_note = None

    semantic_role = sanitized.get("semantic_role")
    if semantic_role is not None:
        allowed_roles = {role.value for role in QuantitySemanticRole}
        if semantic_role not in allowed_roles:
            invalid_note = f"ignored_invalid_semantic_role:{sanitized.get('quantity_id', 'unknown')}:{semantic_role}"
            sanitized.pop("semantic_role", None)

    return sanitized, invalid_note


def _sanitize_latent_quantity_payload(
    latent_quantity: dict,
    *,
    existing_quantity_ids: set[str],
) -> tuple[dict | None, str | None]:
    quantity_id = str(latent_quantity.get("quantity_id", "")).strip()
    if not quantity_id:
        return None, "ignored_invalid_latent_quantity:missing_quantity_id"
    if quantity_id in existing_quantity_ids:
        return None, f"ignored_duplicate_latent_quantity:{quantity_id}"

    surface_text = str(latent_quantity.get("surface_text", "")).strip()
    if not surface_text:
        return None, f"ignored_invalid_latent_quantity:{quantity_id}:missing_surface_text"

    try:
        value = float(latent_quantity.get("value"))
    except (TypeError, ValueError):
        return None, f"ignored_invalid_latent_quantity:{quantity_id}:non_numeric_value"

    payload = {
        "quantity_id": quantity_id,
        "surface_text": surface_text,
        "value": value,
        "unit": latent_quantity.get("unit"),
        "entity_id": latent_quantity.get("entity_id"),
        "semantic_role": latent_quantity.get("semantic_role", QuantitySemanticRole.INTERMEDIATE.value),
        "is_target_candidate": bool(latent_quantity.get("is_target_candidate", False)),
        "notes": _coerce_list_of_strings(latent_quantity.get("notes")),
    }

    semantic_role = payload.get("semantic_role")
    allowed_roles = {role.value for role in QuantitySemanticRole}
    if semantic_role not in allowed_roles:
        payload["semantic_role"] = QuantitySemanticRole.INTERMEDIATE.value
        return payload, f"coerced_invalid_latent_semantic_role:{quantity_id}:{semantic_role}->intermediate"

    return payload, None


def _coerce_list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _schema_validation_result(exc: ValidationError) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ())) or "unknown"
        issues.append(
            GraphValidationIssue(
                code="schema_validation_error",
                message=str(error.get("msg", "Schema validation failed")),
                details={
                    "location": location,
                    "error_type": error.get("type"),
                },
            )
        )
    return GraphValidationResult(
        is_valid=False,
        issues=issues,
        operation_node_count=0,
        notes=["schema_validation_failed"],
    )


def _missing_graph_validation_result() -> GraphValidationResult:
    return GraphValidationResult(
        is_valid=False,
        issues=[
            GraphValidationIssue(
                code="missing_problem_graph",
                message="LLM output must include a typed problem_graph",
            )
        ],
        operation_node_count=0,
        notes=["missing_problem_graph"],
    )


def _graph_feedback_payload(validation_result: GraphValidationResult) -> list[dict]:
    return [issue.model_dump(mode="json") for issue in validation_result.issues]


_PARTIAL_PLAN_MARKERS = (
    "scaffold",
    "later step",
    "later steps",
    "complete plan omitted",
    "estimate",
    "placeholder",
    "to be completed",
)

_SEMANTIC_QUANTITY_ORIGINS = {"observed", "latent", "derived"}
_NULLISH_TEXT = {"", "none", "null", "n/a", "na"}


def _payload_issue(
    code: str,
    message: str,
    *,
    step_id: str | None = None,
    node_id: str | None = None,
    **details,
) -> GraphValidationIssue:
    return GraphValidationIssue(
        code=code,
        message=message,
        step_id=step_id,
        node_id=node_id,
        details=details,
    )


def _grounding_text_present(problem_text: str, candidate: object) -> bool:
    text = str(candidate or "").strip().lower()
    if not text:
        return False
    return text in problem_text.strip().lower()


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _NULLISH_TEXT:
        return None
    return text


def _evaluate_payload_expression(expression: str, environment: dict[str, float]) -> float:
    parsed = ast.parse(expression, mode="eval")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in environment:
                raise KeyError(node.id)
            return float(environment[node.id])
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            raise ValueError(type(node.op).__name__)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            allowed = {"max": max, "min": min, "abs": abs}
            if node.func.id not in allowed:
                raise ValueError(node.func.id)
            args = [_eval(arg) for arg in node.args]
            return float(allowed[node.func.id](*args))
        raise ValueError(type(node).__name__)

    return float(_eval(parsed))


def validate_llm_semantic_state_payload(
    payload: dict,
    heuristic_problem: FormalizedProblem,
) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    notes = ["semantic_state_checked"]
    problem_text = heuristic_problem.problem_text.strip()
    visible_quantity_ids = {quantity.quantity_id for quantity in heuristic_problem.quantities}
    visible_entity_ids = {entity.entity_id for entity in heuristic_problem.entities}

    entity_blocks = payload.get("entities")
    raw_entities = [item for item in entity_blocks if isinstance(item, dict)] if isinstance(entity_blocks, list) else []
    entity_ids: set[str] = set()
    if not isinstance(entity_blocks, list):
        issues.append(
            _payload_issue(
                "missing_entities",
                "Semantic state payload must include an entities list, even if it is empty.",
            )
        )
    for entity in raw_entities:
        entity_id = str(entity.get("entity_id", "")).strip()
        if not entity_id:
            issues.append(_payload_issue("missing_entity_id", "Each entity must include a non-empty entity_id."))
            continue
        if entity_id in entity_ids:
            issues.append(
                _payload_issue(
                    "duplicate_entity_id",
                    "Semantic state contains duplicate entity ids.",
                    node_id=entity_id,
                )
            )
            continue
        entity_ids.add(entity_id)

        surface_text = str(entity.get("surface_text", "")).strip()
        normalized_name = str(entity.get("normalized_name", "")).strip()
        grounding = str(entity.get("grounding", "")).strip()
        if not surface_text and not normalized_name:
            issues.append(
                _payload_issue(
                    "missing_entity_surface_text",
                    "Each entity must include surface_text or normalized_name.",
                    node_id=entity_id,
                )
            )
        if surface_text or grounding:
            if not (
                _grounding_text_present(problem_text, surface_text)
                or _grounding_text_present(problem_text, grounding)
            ):
                notes.append(f"entity_grounding_weak:{entity_id}")
        elif entity_id in visible_entity_ids:
            notes.append(f"entity_anchor_only:{entity_id}")

    target_block = payload.get("target")
    target_variable = None
    if not isinstance(target_block, dict):
        issues.append(
            _payload_issue(
                "missing_target_spec",
                "Semantic state payload must include a target object.",
            )
        )
    else:
        target_variable = str(target_block.get("target_variable", "")).strip() or None
        if target_variable is None:
            issues.append(
                _payload_issue(
                    "missing_target_variable",
                    "Semantic state target must include a non-empty target_variable.",
                )
            )
        target_surface_text = str(target_block.get("surface_text", "")).strip()
        if not target_surface_text:
            issues.append(
                _payload_issue(
                    "missing_target_surface_text",
                    "Semantic state target must include a non-empty surface_text.",
                    node_id=target_variable,
                )
            )
        target_entity_id = _normalize_optional_text(target_block.get("entity_id"))
        if target_entity_id is not None and target_entity_id not in entity_ids:
            issues.append(
                _payload_issue(
                    "unknown_target_entity",
                    "target.entity_id must reference an entity declared in the semantic state.",
                    node_id=target_variable,
                    entity_id=target_entity_id,
                )
            )

    quantities_block = payload.get("quantities")
    quantity_blocks = [item for item in quantities_block if isinstance(item, dict)] if isinstance(quantities_block, list) else []
    quantity_ids: set[str] = set()
    target_candidate_quantity_ids: list[str] = []
    if not quantity_blocks:
        issues.append(
            _payload_issue(
                "missing_quantities",
                "Semantic state payload must include a canonical quantities list.",
                node_id=target_variable,
            )
        )

    for quantity in quantity_blocks:
        quantity_id = str(quantity.get("quantity_id", "")).strip()
        if not quantity_id:
            issues.append(_payload_issue("missing_quantity_id", "Each quantity must include a non-empty quantity_id."))
            continue
        if quantity_id in quantity_ids:
            issues.append(
                _payload_issue(
                    "duplicate_quantity_id",
                    "Semantic state contains duplicate quantity ids.",
                    node_id=quantity_id,
                )
            )
            continue
        quantity_ids.add(quantity_id)

        surface_text = str(quantity.get("surface_text", "")).strip()
        if not surface_text:
            issues.append(
                _payload_issue(
                    "missing_quantity_surface_text",
                    "Each semantic-state quantity must include a non-empty surface_text.",
                    node_id=quantity_id,
                )
            )

        try:
            quantity_value = float(quantity.get("value"))
        except (TypeError, ValueError):
            issues.append(
                _payload_issue(
                    "non_numeric_quantity_value",
                    "Each semantic-state quantity must include a numeric value.",
                    node_id=quantity_id,
                )
            )
            quantity_value = None

        semantic_role = str(quantity.get("semantic_role", QuantitySemanticRole.UNKNOWN.value)).strip()
        allowed_roles = {role.value for role in QuantitySemanticRole}
        if semantic_role and semantic_role not in allowed_roles:
            issues.append(
                _payload_issue(
                    "invalid_quantity_semantic_role",
                    "Semantic-state quantity semantic_role must use an allowed enum value.",
                    node_id=quantity_id,
                    semantic_role=semantic_role,
                )
            )

        origin = str(quantity.get("origin", "")).strip().lower()
        if origin not in _SEMANTIC_QUANTITY_ORIGINS:
            issues.append(
                _payload_issue(
                    "invalid_quantity_origin",
                    "Semantic-state quantity origin must be one of observed, latent, or derived.",
                    node_id=quantity_id,
                    origin=origin,
                )
            )

        entity_id = _normalize_optional_text(quantity.get("entity_id"))
        if entity_id is not None and entity_id not in entity_ids:
            issues.append(
                _payload_issue(
                    "unknown_quantity_entity",
                    "quantity.entity_id must reference an entity declared in the semantic state.",
                    node_id=quantity_id,
                    entity_id=entity_id,
                )
            )

        evidence_ref = _normalize_optional_text(quantity.get("evidence_ref"))
        grounding = _normalize_optional_text(quantity.get("grounding")) or ""
        if bool(quantity.get("is_target_candidate")):
            target_candidate_quantity_ids.append(quantity_id)
        if origin == "observed":
            if evidence_ref is not None and evidence_ref in visible_quantity_ids:
                notes.append(f"observed_quantity_anchor:{quantity_id}->{evidence_ref}")
            elif evidence_ref is not None:
                notes.append(f"weak_quantity_anchor:{quantity_id}->{evidence_ref}")
            elif _grounding_text_present(problem_text, surface_text) or _grounding_text_present(problem_text, grounding):
                notes.append(f"observed_quantity_text_grounded:{quantity_id}")
            else:
                notes.append(f"observed_quantity_grounding_weak:{quantity_id}")

    structure_blocks = payload.get("semantic_structure")
    raw_structures = [item for item in structure_blocks if isinstance(item, dict)] if isinstance(structure_blocks, list) else []
    structure_ids: set[str] = set()
    if not isinstance(structure_blocks, list):
        issues.append(
            _payload_issue(
                "missing_semantic_structure",
                "Semantic state payload must include a semantic_structure list, even if it is empty.",
                node_id=target_variable,
            )
        )
    for structure in raw_structures:
        structure_id = str(structure.get("structure_id", "")).strip()
        if not structure_id:
            issues.append(
                _payload_issue(
                    "missing_structure_id",
                    "Each semantic_structure item must include a non-empty structure_id.",
                    node_id=target_variable,
                )
            )
            continue
        if structure_id in structure_ids:
            issues.append(
                _payload_issue(
                    "duplicate_structure_id",
                    "Semantic state contains duplicate structure ids.",
                    node_id=target_variable,
                    structure_id=structure_id,
                )
            )
            continue
        structure_ids.add(structure_id)

        structure_type = _normalize_optional_text(structure.get("structure_type")) or "unknown"
        notes.append(f"semantic_structure_type:{structure_id}:{structure_type}")

        input_quantity_ids = structure.get("input_quantity_ids")
        if not isinstance(input_quantity_ids, list):
            issues.append(
                _payload_issue(
                    "missing_structure_inputs",
                    "Each semantic_structure item must include input_quantity_ids.",
                    node_id=target_variable,
                    structure_id=structure_id,
                )
            )
        else:
            unknown_inputs = [
                ref for ref in (_normalize_optional_text(item) for item in input_quantity_ids)
                if ref is not None and ref not in quantity_ids
            ]
            if unknown_inputs:
                issues.append(
                    _payload_issue(
                        "unknown_structure_input_quantity",
                        "semantic_structure.input_quantity_ids must reference quantities declared in the semantic state.",
                        node_id=target_variable,
                        structure_id=structure_id,
                        unknown_refs=unknown_inputs,
                    )
                )

        output_quantity_id = _normalize_optional_text(structure.get("output_quantity_id"))
        if output_quantity_id is None:
            issues.append(
                _payload_issue(
                    "missing_structure_output_quantity",
                    "Each semantic_structure item must include output_quantity_id.",
                    node_id=target_variable,
                    structure_id=structure_id,
                )
            )
        elif output_quantity_id not in quantity_ids:
            issues.append(
                _payload_issue(
                    "unknown_structure_output_quantity",
                    "semantic_structure.output_quantity_id must reference a quantity declared in the semantic state.",
                    node_id=target_variable,
                    structure_id=structure_id,
                    output_quantity_id=output_quantity_id,
                )
            )

        parameter_quantity_id = _normalize_optional_text(structure.get("parameter_quantity_id"))
        if parameter_quantity_id is not None and parameter_quantity_id not in quantity_ids:
            issues.append(
                _payload_issue(
                    "unknown_structure_parameter_quantity",
                    "semantic_structure.parameter_quantity_id must reference a quantity declared in the semantic state.",
                    node_id=target_variable,
                    structure_id=structure_id,
                    parameter_quantity_id=parameter_quantity_id,
                )
            )

    if isinstance(target_block, dict):
        target_quantity_id = _normalize_optional_text(target_block.get("target_quantity_id"))
        if target_quantity_id is not None and target_quantity_id not in quantity_ids:
            issues.append(
                _payload_issue(
                    "unknown_target_quantity",
                    "target.target_quantity_id must reference a quantity declared in the semantic state.",
                    node_id=target_variable,
                    target_quantity_id=target_quantity_id,
                )
            )
        if target_quantity_id is None:
            if len(target_candidate_quantity_ids) == 1:
                issues.append(
                    _payload_issue(
                        "missing_target_quantity_link",
                        "target.target_quantity_id must reference the declared target-candidate quantity when the semantic state exposes exactly one such quantity.",
                        node_id=target_variable,
                        candidate_quantity_id=target_candidate_quantity_ids[0],
                    )
                )
            elif len(target_candidate_quantity_ids) > 1:
                issues.append(
                    _payload_issue(
                        "ambiguous_target_quantity_link",
                        "target.target_quantity_id is required when multiple semantic-state quantities are marked as target candidates.",
                        node_id=target_variable,
                        candidate_quantity_ids=target_candidate_quantity_ids,
                    )
                )
        elif target_quantity_id not in target_candidate_quantity_ids:
            notes.append(f"target_quantity_not_marked_candidate:{target_quantity_id}")

    relation_block = payload.get("relation")
    if not isinstance(relation_block, dict):
        notes.append("relation_summary_missing")
    else:
        relation_target = str(relation_block.get("target_variable", "")).strip()
        if target_variable and relation_target != target_variable:
            notes.append(f"soft_relation_target_mismatch:{relation_target}->{target_variable}")
        relation_type = _normalize_optional_text(relation_block.get("relation_type"))
        if relation_type is not None:
            allowed_relation_types = {relation.value for relation in RelationType}
            if relation_type not in allowed_relation_types:
                notes.append(f"soft_invalid_relation_type:{relation_type}")
        operation_hint = _normalize_optional_text(relation_block.get("operation_hint"))
        if operation_hint is not None:
            allowed_operation_hints = {operation.value for operation in OperationType}
            if operation_hint not in allowed_operation_hints:
                notes.append(f"soft_invalid_operation_hint:{operation_hint}")
        source_quantity_ids = relation_block.get("source_quantity_ids")
        if isinstance(source_quantity_ids, list):
            normalized_refs = [_normalize_optional_text(ref) for ref in source_quantity_ids]
            unknown_relation_refs = [ref for ref in normalized_refs if ref is not None and ref not in quantity_ids]
            if unknown_relation_refs:
                notes.append(
                    "soft_relation_unknown_source_quantity:" + ",".join(sorted(unknown_relation_refs))
                )
        if _normalize_optional_text(relation_block.get("expression")) is not None:
            notes.append("ignored_relation_expression")

    forbidden_keys = [
        key
        for key in (
            "quantity_annotations",
            "semantic_facts",
            "plan_steps",
            "graph_target_node_id",
            "graph_notes",
            "assumptions",
        )
        if key in payload
    ]
    if forbidden_keys:
        issues.append(
            _payload_issue(
                "semantic_state_contains_commitment_fields",
                "Semantic state payload must not include executable commitment fields.",
                node_id=target_variable,
                keys=forbidden_keys,
            )
        )

    return GraphValidationResult(
        is_valid=not issues,
        issues=issues,
        target_node_id=target_variable,
        operation_node_count=0,
        notes=notes,
    )


def validate_llm_semantic_commitment_payload(
    payload: dict,
    semantic_payload: dict,
) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    notes = ["semantic_commitment_checked"]

    target_block = semantic_payload.get("target")
    target_variable = None
    if isinstance(target_block, dict):
        target_variable = str(target_block.get("target_variable", "")).strip() or None

    raw_plan_steps = payload.get("plan_steps")
    plan_steps = [step for step in raw_plan_steps if isinstance(step, dict)] if isinstance(raw_plan_steps, list) else []
    if not plan_steps:
        issues.append(
            _payload_issue(
                "missing_plan_steps",
                "LLM payload must include a complete executable plan_steps sequence.",
                node_id=target_variable,
            )
        )

    text_blocks: list[str] = []
    for key in ("notes", "graph_notes", "assumptions"):
        value = payload.get(key)
        if isinstance(value, list):
            text_blocks.extend(str(item) for item in value if str(item).strip())
    relation_block = semantic_payload.get("relation")
    if isinstance(relation_block, dict) and relation_block.get("rationale"):
        text_blocks.append(str(relation_block.get("rationale")))

    lowered_text = " ".join(text_blocks).lower()
    for marker in _PARTIAL_PLAN_MARKERS:
        if marker in lowered_text:
            issues.append(
                _payload_issue(
                    "partial_plan_language",
                    "LLM payload describes the plan as partial instead of committed and executable.",
                    node_id=target_variable,
                    marker=marker,
                )
            )
            break

    environment: dict[str, float] = {}
    quantity_origins: dict[str, str] = {}
    semantic_quantities = semantic_payload.get("quantities")
    if isinstance(semantic_quantities, list):
        for raw_quantity in semantic_quantities:
            if not isinstance(raw_quantity, dict):
                continue
            quantity_id = str(raw_quantity.get("quantity_id", "")).strip()
            if not quantity_id:
                continue
            quantity_origins[quantity_id] = str(raw_quantity.get("origin", "")).strip().lower()
            try:
                quantity_value = float(raw_quantity.get("value"))
            except (TypeError, ValueError):
                continue
            if quantity_origins[quantity_id] == "observed":
                environment[quantity_id] = quantity_value

    required_materialized_refs: set[str] = set()
    semantic_structures = semantic_payload.get("semantic_structure")
    if isinstance(semantic_structures, list):
        for raw_structure in semantic_structures:
            if not isinstance(raw_structure, dict):
                continue
            output_quantity_id = _normalize_optional_text(raw_structure.get("output_quantity_id"))
            if output_quantity_id is None:
                continue
            if quantity_origins.get(output_quantity_id) != "observed":
                required_materialized_refs.add(output_quantity_id)

    target_quantity_id: str | None = None
    if isinstance(target_block, dict):
        target_quantity_id = _normalize_optional_text(target_block.get("target_quantity_id"))
        if target_quantity_id is not None and quantity_origins.get(target_quantity_id) != "observed":
            required_materialized_refs.add(target_quantity_id)

    notes.append(f"initial_observed_refs={len(environment)}")

    seen_step_ids: set[str] = set()
    seen_step_indexes: set[int] = set()
    produced_refs: set[str] = set()
    final_value: float | None = None

    ordered_plan_steps = sorted(plan_steps, key=lambda item: int(item.get("step_index", 0) or 0))

    for step in ordered_plan_steps:
        step_id = str(step.get("step_id", "")).strip()
        if not step_id:
            issues.append(_payload_issue("missing_step_id", "Each plan step must include a non-empty step_id."))
            continue
        if step_id in seen_step_ids:
            issues.append(_payload_issue("duplicate_step_id", "LLM payload contains duplicate plan step ids.", step_id=step_id))
        seen_step_ids.add(step_id)

        try:
            step_index = int(step.get("step_index", 0) or 0)
        except (TypeError, ValueError):
            step_index = 0
        if step_index <= 0:
            issues.append(
                _payload_issue("invalid_step_index", "Each plan step must include a positive step_index.", step_id=step_id)
            )
        elif step_index in seen_step_indexes:
            issues.append(
                _payload_issue("duplicate_step_index", "LLM payload contains duplicate plan step indexes.", step_id=step_id)
            )
        else:
            seen_step_indexes.add(step_index)

        output_ref = str(step.get("output_ref", "")).strip()
        if not output_ref:
            issues.append(
                _payload_issue("missing_step_output_ref", "Each plan step must produce an output_ref.", step_id=step_id)
            )
            continue

        input_refs = [str(ref).strip() for ref in step.get("input_refs", []) if str(ref).strip()]
        missing_refs = [ref for ref in input_refs if ref not in environment]
        if missing_refs:
            issues.append(
                _payload_issue(
                    "input_not_available",
                    "Plan step references inputs that are not available yet in the committed payload.",
                    step_id=step_id,
                    missing_refs=missing_refs,
                )
            )
            continue

        expression = str(step.get("expression", "")).strip()
        if not expression:
            issues.append(
                _payload_issue("missing_step_expression", "Each plan step must include an executable expression.", step_id=step_id)
            )
            continue
        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            issues.append(
                _payload_issue(
                    "expression_evaluation_failed",
                    "Plan expression could not be parsed under the committed payload environment.",
                    step_id=step_id,
                    error=str(exc),
                )
            )
            continue
        referenced_symbols = sorted({node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)})
        missing_declared_inputs = [symbol for symbol in referenced_symbols if symbol not in input_refs]
        if missing_declared_inputs:
            issues.append(
                _payload_issue(
                    "expression_symbol_missing_from_inputs",
                    "Each non-constant symbol in a plan expression must appear explicitly in input_refs.",
                    step_id=step_id,
                    missing_symbols=missing_declared_inputs,
                )
            )
            continue
        try:
            final_value = _evaluate_payload_expression(expression, environment)
        except KeyError as exc:
            issues.append(
                _payload_issue(
                    "expression_unknown_reference",
                    "Plan expression references an unavailable symbol.",
                    step_id=step_id,
                    missing_ref=str(exc),
                )
            )
            continue
        except Exception as exc:
            issues.append(
                _payload_issue(
                    "expression_evaluation_failed",
                    "Plan expression could not be evaluated under the committed payload environment.",
                    step_id=step_id,
                    error=str(exc),
                )
            )
            continue

        environment[output_ref] = final_value
        produced_refs.add(output_ref)

    accepted_terminal_refs = {
        ref
        for ref in (
            target_variable,
            target_quantity_id,
        )
        if ref is not None
    }

    if ordered_plan_steps:
        final_output_ref = str(ordered_plan_steps[-1].get("output_ref", "")).strip()
        if accepted_terminal_refs and final_output_ref not in accepted_terminal_refs:
            issues.append(
                _payload_issue(
                    "final_step_target_mismatch",
                    "The final plan step must output either the declared target_variable or the declared target_quantity_id directly.",
                    node_id=target_variable,
                    final_output_ref=final_output_ref,
                )
            )

    if accepted_terminal_refs and not (produced_refs & accepted_terminal_refs):
        issues.append(
            _payload_issue(
                "target_not_produced",
                "Committed plan_steps do not produce the declared target_variable or target_quantity_id directly.",
                node_id=target_variable,
            )
        )

    missing_materialized_refs = sorted(ref for ref in required_materialized_refs if ref not in produced_refs)
    if missing_materialized_refs:
        issues.append(
            _payload_issue(
                "structure_not_materialized",
                "Committed plan_steps must materialize the non-observed semantic quantities implied by semantic_structure and the target quantity.",
                node_id=target_variable,
                missing_refs=missing_materialized_refs,
            )
        )

    return GraphValidationResult(
        is_valid=not issues,
        issues=issues,
        target_node_id=target_variable,
        operation_node_count=len(ordered_plan_steps),
        notes=notes,
    )


def validate_formalized_problem(problem: FormalizedProblem) -> FormalizedProblem:
    notes = list(problem.notes)

    deduped_entities: list[ProblemEntity] = []
    seen_entities: set[str] = set()
    for entity in problem.entities:
        key = (entity.normalized_name or entity.surface_text).strip().lower()
        if key in seen_entities:
            notes.append(f"deduped_entity:{key}")
            continue
        seen_entities.add(key)
        deduped_entities.append(entity)

    quantities, quantity_notes = _dedupe_quantities(list(problem.quantities))
    notes.extend(quantity_notes)
    if not quantities:
        notes.append("no_quantities_extracted")

    target = problem.target
    if target is None:
        target = TargetSpec(
            surface_text=problem.problem_text.strip(),
            normalized_question=problem.problem_text.strip(),
            target_variable="answer",
            provenance=ProvenanceSource.UNKNOWN,
            confidence=0.1,
        )
        notes.append("target_missing_fallback")

    relation_candidates = list(problem.relation_candidates)
    if not relation_candidates:
        problem = problem.model_copy(
            update={
                "relation_candidates": [
                    RelationCandidate(
                        relation_id="relation_fallback",
                        relation_type=RelationType.UNKNOWN,
                        operation_hint=OperationType.UNKNOWN,
                        source_quantity_ids=[q.quantity_id for q in quantities],
                        target_variable=target.target_variable,
                        confidence=0.1,
                        provenance=ProvenanceSource.UNKNOWN,
                        rationale="Fallback relation candidate due to missing inferred relation.",
                    )
                ]
            }
        )
        notes.append("relation_candidate_fallback")
        relation_candidates = list(problem.relation_candidates)

    for index, relation in enumerate(relation_candidates):
        expression = relation.expression
        if relation.target_variable == target.target_variable and not expression and quantities:
            expression = f"{target.target_variable} = unresolved_relation({', '.join(q.quantity_id for q in quantities)})"
            notes.append(f"filled_expression_for:{relation.relation_id}")
        relation_candidates[index] = relation.model_copy(update={"expression": expression})

    confidence = 0.15
    if quantities:
        confidence += 0.25
    if len(quantities) >= 2:
        confidence += 0.15
    if target and target.provenance != ProvenanceSource.UNKNOWN:
        confidence += 0.15
    if any("percent_like" in note for quantity in quantities for note in quantity.notes):
        notes.append("contains_percent_like_evidence")
    if any("threshold_like" in note for quantity in quantities for note in quantity.notes):
        notes.append("contains_threshold_like_evidence")

    return problem.model_copy(
        update={
            "entities": deduped_entities,
            "quantities": quantities,
            "target": target,
            "relation_candidates": relation_candidates,
            "confidence": max(problem.confidence, min(confidence, 0.92)),
            "notes": notes,
        }
    )


def _heuristic_graph_operation_steps(problem: FormalizedProblem):
    if problem.problem_graph is None:
        return []
    return [
        node
        for node in problem.problem_graph.nodes
        if node.node_type == ProblemGraphNodeType.OPERATION
    ]


def _compare_with_heuristic_notes(
    problem: FormalizedProblem,
    heuristic_problem: FormalizedProblem,
) -> list[str]:
    notes: list[str] = []
    heuristic_quantities = {quantity.quantity_id: quantity for quantity in heuristic_problem.quantities}

    for quantity in problem.quantities:
        heuristic_quantity = heuristic_quantities.get(quantity.quantity_id)
        if heuristic_quantity is None:
            continue
        if quantity.semantic_role != heuristic_quantity.semantic_role:
            notes.append(
                "heuristic_disagreement:quantity_role:"
                f"{quantity.quantity_id}:{heuristic_quantity.semantic_role.value}->{quantity.semantic_role.value}"
            )
        if quantity.unit != heuristic_quantity.unit:
            notes.append(
                f"heuristic_disagreement:quantity_unit:{quantity.quantity_id}:{heuristic_quantity.unit}->{quantity.unit}"
            )

    if problem.target is not None and heuristic_problem.target is not None:
        if problem.target.target_variable != heuristic_problem.target.target_variable:
            notes.append(
                "heuristic_disagreement:target_variable:"
                f"{heuristic_problem.target.target_variable}->{problem.target.target_variable}"
            )
        if problem.target.target_quantity_id != heuristic_problem.target.target_quantity_id:
            notes.append(
                "heuristic_disagreement:target_quantity_id:"
                f"{heuristic_problem.target.target_quantity_id}->{problem.target.target_quantity_id}"
            )

    if problem.relation_candidates and heuristic_problem.relation_candidates:
        current = problem.relation_candidates[0]
        heuristic = heuristic_problem.relation_candidates[0]
        if current.relation_type != heuristic.relation_type:
            notes.append(
                "heuristic_disagreement:relation_type:"
                f"{heuristic.relation_type.value}->{current.relation_type.value}"
            )
        if current.operation_hint != heuristic.operation_hint:
            notes.append(
                "heuristic_disagreement:operation_hint:"
                f"{heuristic.operation_hint.value}->{current.operation_hint.value}"
            )

    current_steps = len(_heuristic_graph_operation_steps(problem))
    heuristic_steps = len(_heuristic_graph_operation_steps(heuristic_problem))
    if current_steps != heuristic_steps:
        notes.append(f"heuristic_disagreement:graph_step_count:{heuristic_steps}->{current_steps}")

    return notes


def _apply_local_semantic_repairs(problem: FormalizedProblem) -> FormalizedProblem:
    return problem


def _semantic_sanity_validation_result(problem: FormalizedProblem) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    graph_steps = _heuristic_graph_operation_steps(problem)

    if problem.target is None:
        issues.append(
            GraphValidationIssue(
                code="missing_target_spec",
                message="Formalized problem must include a target.",
            )
        )

    return GraphValidationResult(
        is_valid=not issues,
        issues=issues,
        target_node_id=problem.problem_graph.target_node_id if problem.problem_graph is not None else None,
        operation_node_count=len(graph_steps),
        notes=["semantic_sanity_checked"],
    )
