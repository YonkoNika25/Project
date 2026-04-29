"""Builders for heuristic drafts and semantic-state compilation."""
from __future__ import annotations

from src.formalizer.problem_graph import build_problem_graph
from src.formalizer.problem_formalizer_extractors import (
    _build_problem_anchor_evidence,
    _build_relation_candidates,
    _build_target_spec,
    _extract_entities,
    _extract_quantities,
    _extract_target_text,
    _link_quantities_to_entities,
    _project_quantities_from_evidence,
    _project_relation_candidates_from_evidence,
    _project_target_from_evidence,
)
from src.formalizer.problem_formalizer_validation import (
    _apply_local_semantic_repairs,
    _coerce_list_of_strings,
    _compare_with_heuristic_notes,
    _sanitize_quantity_update,
    validate_formalized_problem,
)
from src.models import (
    FormalizedProblem,
    OperationType,
    ProblemEntity,
    ProblemGraph,
    ProblemGraphEdge,
    ProblemGraphEdgeType,
    ProblemGraphNode,
    ProblemGraphNodeType,
    ProvenanceSource,
    QuantityAnnotation,
    QuantitySemanticRole,
    RelationCandidate,
    RelationType,
    TargetSpec,
    TraceOperation,
)

_NULLISH_TEXT = {"", "none", "null", "n/a", "na"}


def _normalize_step_expression(expression: object) -> str:
    text = str(expression or "").strip()
    if "=" in text:
        _, rhs = text.split("=", 1)
        text = rhs.strip()
    return text


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _NULLISH_TEXT:
        return None
    return text


def _normalize_relation_expression(expression: object) -> str | None:
    text = str(expression or "").strip()
    if not text:
        return None
    if "=" in text:
        lhs, rhs = text.split("=", 1)
        lhs = lhs.strip()
        rhs = rhs.strip()
        return f"{lhs} = {rhs}" if lhs and rhs else text
    return text


def _coerce_relation_type(value: object) -> str:
    text = _normalize_optional_text(value)
    try:
        return RelationType(text or RelationType.UNKNOWN.value).value
    except ValueError:
        return RelationType.UNKNOWN.value


def _coerce_operation_hint(value: object) -> str:
    text = _normalize_optional_text(value)
    try:
        return OperationType(text or OperationType.UNKNOWN.value).value
    except ValueError:
        return OperationType.UNKNOWN.value


def _normalize_graph_steps_for_builder(
    graph_steps: list[dict],
    *,
    target_variable: str | None,
    target_quantity_id: str | None,
) -> tuple[list[dict], list[str]]:
    normalized_steps: list[dict] = []
    notes: list[str] = []
    produced_refs: set[str] = set()
    seen_step_ids: set[str] = set()

    for step in graph_steps:
        normalized_step = dict(step)
        normalized_step["expression"] = _normalize_step_expression(step.get("expression"))
        normalized_inputs = [str(ref).strip() for ref in step.get("input_refs", []) if str(ref).strip()]
        normalized_output_ref = str(step.get("output_ref", "")).strip()
        step_id = str(step.get("step_id", "")).strip()
        if target_variable:
            normalized_inputs = [target_variable if ref == "target" else ref for ref in normalized_inputs]
            if normalized_output_ref == "target":
                normalized_output_ref = target_variable
        normalized_step["input_refs"] = normalized_inputs
        normalized_step["output_ref"] = normalized_output_ref
        normalized_steps.append(normalized_step)
        if step_id:
            seen_step_ids.add(step_id)
        if normalized_output_ref:
            produced_refs.add(normalized_output_ref)

    if (
        target_variable
        and target_quantity_id
        and target_variable not in produced_refs
        and target_quantity_id in produced_refs
    ):
        next_step_index = 1 + max(
            (int(step.get("step_index", 0) or 0) for step in normalized_steps),
            default=0,
        )
        alias_step_id = "bind_target_variable"
        suffix = 2
        while alias_step_id in seen_step_ids:
            alias_step_id = f"bind_target_variable_{suffix}"
            suffix += 1
        normalized_steps.append(
            {
                "step_id": alias_step_id,
                "step_index": next_step_index,
                "operation": TraceOperation.DERIVE.value,
                "label": "Bind target variable to the declared target quantity.",
                "input_refs": [target_quantity_id],
                "output_ref": target_variable,
                "expression": target_quantity_id,
                "confidence": 0.85,
            }
        )
        notes.append(f"local_target_binding:{target_quantity_id}->{target_variable}")

    return normalized_steps, notes


def _build_target_payload_from_sketch(
    payload: dict,
) -> dict:
    target_block = payload.get("target")
    if not isinstance(target_block, dict):
        raise ValueError("semantic state payload must include a target object")
    target_payload = {
        key: value
        for key, value in target_block.items()
        if key
        in {
            "surface_text",
            "normalized_question",
            "target_variable",
            "target_quantity_id",
            "entity_id",
            "unit",
            "description",
            "confidence",
        }
    }
    if "target_quantity_id" in target_payload:
        target_payload["target_quantity_id"] = _normalize_optional_text(target_payload.get("target_quantity_id"))
    if "entity_id" in target_payload:
        target_payload["entity_id"] = _normalize_optional_text(target_payload.get("entity_id"))
    if "unit" in target_payload:
        target_payload["unit"] = _normalize_optional_text(target_payload.get("unit"))
    return target_payload


def _build_relation_candidates_from_semantic_state(
    payload: dict,
    *,
    target_variable: str | None,
    quantities: list[QuantityAnnotation],
) -> list[RelationCandidate]:
    relation_block = payload.get("relation")
    raw_relations: list[dict] = []
    if isinstance(relation_block, dict):
        raw_relations = [relation_block]

    if not raw_relations:
        raw_relations = [{}]

    relation_candidates: list[RelationCandidate] = []
    known_quantity_ids = {quantity.quantity_id for quantity in quantities}
    for index, raw_relation in enumerate(raw_relations, start=1):
        raw_source_quantity_ids = raw_relation.get("source_quantity_ids")
        normalized_source_refs = [
            ref
            for ref in (_normalize_optional_text(item) for item in raw_source_quantity_ids or [])
            if ref is not None and ref in known_quantity_ids
        ]
        relation_payload = {
            "relation_id": raw_relation.get("relation_id") or f"relation_{index}",
            "relation_type": _coerce_relation_type(raw_relation.get("relation_type")),
            "operation_hint": _coerce_operation_hint(raw_relation.get("operation_hint")),
            "source_quantity_ids": normalized_source_refs or [quantity.quantity_id for quantity in quantities],
            "target_variable": target_variable,
            "expression": None,
            "rationale": raw_relation.get("rationale"),
            "confidence": raw_relation.get("confidence", 0.75),
            "provenance": ProvenanceSource.LLM.value,
        }
        relation_candidates.append(RelationCandidate.model_validate(relation_payload))
    return relation_candidates


def _compile_entities_from_semantic_state(
    payload: dict,
    notes: list[str],
) -> list[ProblemEntity]:
    raw_entities = payload.get("entities")
    if not isinstance(raw_entities, list):
        raise ValueError("semantic state payload must include an entities list")

    entities: list[ProblemEntity] = []
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            raise ValueError("entities must contain objects only")
        entity_id = str(raw_entity.get("entity_id", "")).strip()
        if not entity_id:
            raise ValueError("each entity must include a non-empty entity_id")
        surface_text = str(raw_entity.get("surface_text", "")).strip()
        normalized_name = _normalize_optional_text(raw_entity.get("normalized_name"))
        if not surface_text and normalized_name is not None:
            surface_text = normalized_name
        if not surface_text:
            raise ValueError(f"entity '{entity_id}' must include surface_text or normalized_name")
        grounding = _normalize_optional_text(raw_entity.get("grounding"))
        entity_notes = _coerce_list_of_strings(raw_entity.get("notes"))
        if grounding:
            entity_notes.append(f"semantic_state_grounding:{grounding}")
        entities.append(
            ProblemEntity.model_validate(
                {
                    "entity_id": entity_id,
                    "surface_text": surface_text,
                    "normalized_name": normalized_name,
                    "entity_type": raw_entity.get("entity_type", "unknown"),
                    "aliases": _coerce_list_of_strings(raw_entity.get("aliases")),
                    "metadata": {"notes": entity_notes} if entity_notes else {},
                }
            )
        )
        notes.append(f"llm_entity_defined:{entity_id}")

    return entities


def _compile_quantities_from_semantic_state(
    heuristic_problem: FormalizedProblem,
    payload: dict,
    notes: list[str],
) -> list[QuantityAnnotation]:
    raw_quantities = payload.get("quantities")
    if not isinstance(raw_quantities, list):
        raise ValueError("semantic state payload must include a quantities list")

    heuristic_quantities_by_id = {
        quantity.quantity_id: quantity for quantity in heuristic_problem.quantities
    }
    quantities: list[QuantityAnnotation] = []

    for raw_quantity in raw_quantities:
        if not isinstance(raw_quantity, dict):
            raise ValueError("quantities must contain objects only")

        quantity_id = str(raw_quantity.get("quantity_id", "")).strip()
        if not quantity_id:
            raise ValueError("each quantity must include a non-empty quantity_id")

        surface_text = str(raw_quantity.get("surface_text", "")).strip()
        if not surface_text:
            raise ValueError(f"quantity '{quantity_id}' must include a non-empty surface_text")

        try:
            value = float(raw_quantity.get("value"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"quantity '{quantity_id}' must include a numeric value") from exc

        sanitized, invalid_note = _sanitize_quantity_update(raw_quantity)
        if invalid_note:
            notes.append(invalid_note)

        quantity_notes = _coerce_list_of_strings(raw_quantity.get("notes"))
        origin = (_normalize_optional_text(raw_quantity.get("origin")) or "").lower()
        if origin:
            quantity_notes.append(f"semantic_state_origin:{origin}")
        grounding = _normalize_optional_text(raw_quantity.get("grounding"))
        if grounding:
            quantity_notes.append(f"semantic_state_grounding:{grounding}")

        anchor_ref = _normalize_optional_text(raw_quantity.get("evidence_ref")) if origin == "observed" else None
        if anchor_ref is None and origin == "observed" and quantity_id in heuristic_quantities_by_id:
            anchor_ref = quantity_id

        anchor_quantity = heuristic_quantities_by_id.get(anchor_ref) if anchor_ref else None
        if anchor_ref:
            quantity_notes.append(f"semantic_state_evidence_ref:{anchor_ref}")

        quantity_payload = {
            "quantity_id": quantity_id,
            "surface_text": surface_text,
            "value": value,
            "unit": _normalize_optional_text(raw_quantity.get("unit")),
            "entity_id": _normalize_optional_text(raw_quantity.get("entity_id")),
            "semantic_role": sanitized.get("semantic_role", QuantitySemanticRole.UNKNOWN.value),
            "is_target_candidate": bool(raw_quantity.get("is_target_candidate", False)),
            "provenance": ProvenanceSource.LLM.value,
            "notes": quantity_notes,
        }

        if anchor_quantity is not None:
            if abs(float(anchor_quantity.value) - float(value)) <= 1e-6:
                if quantity_payload["unit"] is None:
                    quantity_payload["unit"] = anchor_quantity.unit
                quantity_payload["sentence_index"] = anchor_quantity.sentence_index
                quantity_payload["char_start"] = anchor_quantity.char_start
                quantity_payload["char_end"] = anchor_quantity.char_end
                notes.append(f"llm_quantity_grounded_by_anchor:{quantity_id}->{anchor_ref}")
            else:
                notes.append(f"ignored_mismatched_anchor:{quantity_id}->{anchor_ref}")
        elif anchor_ref is not None:
            notes.append(f"ignored_unknown_anchor:{quantity_id}->{anchor_ref}")

        quantities.append(QuantityAnnotation.model_validate(quantity_payload))

    return quantities


def _extract_graph_steps_from_payload(payload: dict) -> list[dict]:
    plan_steps = payload.get("plan_steps")
    if isinstance(plan_steps, list):
        return [step for step in plan_steps if isinstance(step, dict)]
    return []


def _merge_semantic_and_commitment_payloads(
    semantic_payload: dict,
    commitment_payload: dict,
) -> dict:
    merged = dict(semantic_payload)
    merged.update(commitment_payload)

    merged["notes"] = _coerce_list_of_strings(semantic_payload.get("notes")) + _coerce_list_of_strings(
        commitment_payload.get("notes")
    )
    merged["graph_notes"] = _coerce_list_of_strings(commitment_payload.get("graph_notes"))
    merged["assumptions"] = _coerce_list_of_strings(commitment_payload.get("assumptions"))
    merged["plan_steps"] = _extract_graph_steps_from_payload(commitment_payload)
    merged["graph_target_node_id"] = commitment_payload.get("graph_target_node_id")
    merged["graph_confidence"] = commitment_payload.get("graph_confidence")
    merged["confidence"] = commitment_payload.get("confidence", semantic_payload.get("confidence"))
    return merged


def _build_compact_draft(heuristic_problem: FormalizedProblem, evidence_pack: dict) -> dict:
    return {
        "problem_text": heuristic_problem.problem_text,
        "sentence_spans": list(evidence_pack.get("sentence_spans", [])),
        "numeric_mentions": list(evidence_pack.get("numeric_mentions", [])),
        "implicit_quantity_cues": list(evidence_pack.get("implicit_quantity_cues", [])),
        "target_span_candidates": list(evidence_pack.get("target_span_candidates", [])),
        "entity_candidates": list(evidence_pack.get("entity_candidates", [])),
    }


def _build_problem_graph_from_skeleton(
    problem: FormalizedProblem,
    graph_steps: list[dict],
    graph_target_node_id: str | None,
    graph_confidence: float,
    graph_notes: list[str],
) -> ProblemGraph:
    nodes: list[ProblemGraphNode] = []
    edges: list[ProblemGraphEdge] = []

    for entity in problem.entities:
        nodes.append(
            ProblemGraphNode(
                node_id=entity.entity_id,
                node_type=ProblemGraphNodeType.ENTITY,
                label=entity.surface_text,
                entity_id=entity.entity_id,
                confidence=0.95,
                provenance=ProvenanceSource.PROBLEM_TEXT,
                notes=[],
            )
        )

    for quantity in problem.quantities:
        nodes.append(
            ProblemGraphNode(
                node_id=quantity.quantity_id,
                node_type=ProblemGraphNodeType.QUANTITY,
                label=quantity.surface_text,
                value=quantity.value,
                unit=quantity.unit,
                quantity_id=quantity.quantity_id,
                entity_id=quantity.entity_id,
                semantic_role=quantity.semantic_role,
                confidence=0.95,
                provenance=quantity.provenance,
                notes=list(quantity.notes),
            )
        )
        if quantity.entity_id is not None:
            edges.append(
                ProblemGraphEdge(
                    edge_id=f"edge_{quantity.entity_id}_owns_{quantity.quantity_id}",
                    source_node_id=quantity.entity_id,
                    target_node_id=quantity.quantity_id,
                    edge_type=ProblemGraphEdgeType.ENTITY_HAS_QUANTITY,
                    confidence=0.9,
                    provenance=ProvenanceSource.PROBLEM_TEXT,
                    notes=[],
                )
            )

    target_node_id = graph_target_node_id or (problem.target.target_variable if problem.target is not None else None)
    if problem.target is not None:
        nodes.append(
            ProblemGraphNode(
                node_id=problem.target.target_variable,
                node_type=ProblemGraphNodeType.TARGET,
                label=problem.target.surface_text,
                unit=problem.target.unit,
                entity_id=problem.target.entity_id,
                target_variable=problem.target.target_variable,
                confidence=problem.target.confidence,
                provenance=problem.target.provenance,
                notes=[],
            )
        )
        if problem.target.entity_id is not None:
            edges.append(
                ProblemGraphEdge(
                    edge_id=f"edge_{problem.target.target_variable}_describes_{problem.target.entity_id}",
                    source_node_id=problem.target.target_variable,
                    target_node_id=problem.target.entity_id,
                    edge_type=ProblemGraphEdgeType.DESCRIBES_ENTITY,
                    confidence=0.82,
                    provenance=ProvenanceSource.PROBLEM_TEXT,
                    notes=[],
                )
            )

    existing_node_ids = {node.node_id for node in nodes}
    existing_refs = set(existing_node_ids)

    for step in sorted(graph_steps, key=lambda item: int(item.get("step_index", 0) or 0)):
        step_id = str(step.get("step_id", "")).strip()
        operation_name = str(step.get("operation", TraceOperation.UNKNOWN.value)).strip()
        output_ref = str(step.get("output_ref", "")).strip()
        op_node_id = f"op_{step_id}"
        input_refs = [str(ref).strip() for ref in step.get("input_refs", []) if str(ref).strip()]
        label = str(step.get("label", step_id)).strip() or step_id
        expression = str(step.get("expression", "")).strip()

        nodes.append(
            ProblemGraphNode(
                node_id=op_node_id,
                node_type=ProblemGraphNodeType.OPERATION,
                label=label,
                operation=TraceOperation(operation_name),
                expression=expression,
                step_id=step_id,
                step_index=int(step.get("step_index", 1) or 1),
                confidence=float(step.get("confidence", 0.85) or 0.85),
                provenance=ProvenanceSource.LLM,
                notes=[],
            )
        )

        for position, input_ref in enumerate(input_refs):
            if input_ref not in existing_refs:
                continue
            edges.append(
                ProblemGraphEdge(
                    edge_id=f"edge_{input_ref}_to_{op_node_id}_{position}",
                    source_node_id=input_ref,
                    target_node_id=op_node_id,
                    edge_type=ProblemGraphEdgeType.INPUT_TO_OPERATION,
                    position=position,
                    confidence=0.9,
                    provenance=ProvenanceSource.LLM,
                    notes=[],
                )
            )

        if output_ref and output_ref not in existing_node_ids:
            node_type = (
                ProblemGraphNodeType.TARGET
                if problem.target is not None and output_ref == problem.target.target_variable
                else ProblemGraphNodeType.INTERMEDIATE
            )
            nodes.append(
                ProblemGraphNode(
                    node_id=output_ref,
                    node_type=node_type,
                    label=output_ref if node_type == ProblemGraphNodeType.INTERMEDIATE else problem.target.surface_text,
                    unit=step.get("output_unit") if isinstance(step.get("output_unit"), str) else None,
                    target_variable=output_ref if node_type == ProblemGraphNodeType.TARGET else None,
                    confidence=float(step.get("confidence", 0.85) or 0.85),
                    provenance=ProvenanceSource.LLM,
                    notes=[],
                )
            )
            existing_node_ids.add(output_ref)
            existing_refs.add(output_ref)

        if output_ref:
            edges.append(
                ProblemGraphEdge(
                    edge_id=f"edge_{op_node_id}_to_{output_ref}",
                    source_node_id=op_node_id,
                    target_node_id=output_ref,
                    edge_type=ProblemGraphEdgeType.OUTPUT_FROM_OPERATION,
                    confidence=0.9,
                    provenance=ProvenanceSource.LLM,
                    notes=[],
                )
            )
            existing_refs.add(output_ref)

        existing_refs.add(op_node_id)

    return ProblemGraph(
        nodes=nodes,
        edges=edges,
        target_node_id=target_node_id,
        confidence=graph_confidence,
        provenance=ProvenanceSource.LLM,
        notes=graph_notes,
    )


def _build_formalized_problem_from_skeleton(
    problem_text: str,
    heuristic_problem: FormalizedProblem,
    payload: dict,
) -> FormalizedProblem:
    notes = list(heuristic_problem.notes)
    notes.extend(_coerce_list_of_strings(payload.get("notes")))
    entities = _compile_entities_from_semantic_state(payload, notes)
    quantities = _compile_quantities_from_semantic_state(heuristic_problem, payload, notes)
    existing_quantity_ids = {quantity.quantity_id for quantity in quantities}

    target_payload = _build_target_payload_from_sketch(payload)
    target_variable = str(target_payload.get("target_variable", "")).strip()
    target_quantity_id = target_payload.get("target_quantity_id")
    if target_quantity_id is not None and target_quantity_id not in existing_quantity_ids:
        raise ValueError(f"target_quantity_id '{target_quantity_id}' does not exist in semantic-state quantities")
    target_payload["provenance"] = ProvenanceSource.LLM.value
    target = TargetSpec.model_validate(target_payload) if target_payload else None

    relation_candidates = _build_relation_candidates_from_semantic_state(
        payload,
        target_variable=target.target_variable if target is not None else target_variable,
        quantities=quantities,
    )

    graph_steps = _extract_graph_steps_from_payload(payload)
    graph_steps, graph_repair_notes = _normalize_graph_steps_for_builder(
        graph_steps,
        target_variable=target_variable or None,
        target_quantity_id=target_quantity_id if isinstance(target_quantity_id, str) else None,
    )
    notes.extend(graph_repair_notes)
    problem = FormalizedProblem(
        problem_text=problem_text.strip(),
        quantities=quantities,
        entities=entities,
        target=target,
        relation_candidates=relation_candidates,
        assumptions=_coerce_list_of_strings(payload.get("assumptions")),
        confidence=float(payload.get("confidence", heuristic_problem.confidence) or heuristic_problem.confidence),
        provenance=ProvenanceSource.LLM,
        notes=notes,
    )
    problem = validate_formalized_problem(problem)
    graph = _build_problem_graph_from_skeleton(
        problem=problem,
        graph_steps=graph_steps,
        graph_target_node_id=payload.get("graph_target_node_id"),
        graph_confidence=float(payload.get("graph_confidence", problem.confidence) or problem.confidence),
        graph_notes=_coerce_list_of_strings(payload.get("graph_notes")) or ["llm_graph_skeleton"],
    )
    problem = problem.model_copy(update={"problem_graph": graph})
    problem = _apply_local_semantic_repairs(problem)
    comparison_notes = _compare_with_heuristic_notes(problem, heuristic_problem)
    if comparison_notes:
        problem = problem.model_copy(update={"notes": list(problem.notes) + comparison_notes})
    return problem


def _attach_problem_graph(problem: FormalizedProblem) -> FormalizedProblem:
    graph = build_problem_graph(problem)
    return problem.model_copy(update={"problem_graph": graph})


def _heuristic_formalize_problem(problem_text: str) -> tuple[FormalizedProblem, dict]:
    cleaned_text = (problem_text or "").strip()
    evidence_pack = _build_problem_anchor_evidence(cleaned_text)
    target_text = _extract_target_text(cleaned_text)
    quantities = _project_quantities_from_evidence(evidence_pack)
    entities = _extract_entities(cleaned_text)
    quantities = _link_quantities_to_entities(quantities, entities)
    target = _project_target_from_evidence(evidence_pack)
    relation_candidates, relation_notes = _project_relation_candidates_from_evidence(
        evidence_pack,
        quantities,
        target,
    )

    notes = [
        f"sentence_spans_extracted={len(evidence_pack.get('sentence_spans', []))}",
        f"numeric_mentions_extracted={len(evidence_pack.get('numeric_mentions', []))}",
        f"implicit_quantity_cues_extracted={len(evidence_pack.get('implicit_quantity_cues', []))}",
        f"lexical_cues_extracted={len(evidence_pack.get('lexical_cues', []))}",
        f"target_candidates_extracted={len(evidence_pack.get('target_span_candidates', []))}",
        f"target_link_candidates_extracted={len(evidence_pack.get('target_link_candidates', []))}",
        f"relation_candidates_extracted={len(relation_candidates)}",
    ]
    if entities:
        notes.append(f"entities_extracted={len(entities)}")
    if target_text:
        notes.append("target_candidate_selected")
    notes.extend(relation_notes)

    problem = FormalizedProblem(
        problem_text=cleaned_text,
        quantities=quantities,
        entities=entities,
        target=target,
        relation_candidates=relation_candidates,
        assumptions=[],
        confidence=0.0,
        provenance=ProvenanceSource.HEURISTIC,
        notes=notes,
    )
    validated = validate_formalized_problem(problem)
    return _attach_problem_graph(validated), evidence_pack
