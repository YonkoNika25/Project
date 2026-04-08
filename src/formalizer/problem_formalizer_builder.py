"""Builders for heuristic drafts and semantic-sketch compilation."""
from __future__ import annotations

import re

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
    _sanitize_latent_quantity_payload,
    _sanitize_quantity_update,
    validate_formalized_problem,
)
from src.models import (
    FormalizedProblem,
    OperationType,
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


def _normalize_step_expression(expression: object) -> str:
    text = str(expression or "").strip()
    if "=" in text:
        _, rhs = text.split("=", 1)
        text = rhs.strip()
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


def _looks_like_generated_quantity_id(ref: str) -> bool:
    return bool(re.fullmatch(r"quantity_\d+", ref or ""))


def _normalize_graph_steps_for_builder(
    graph_steps: list[dict],
    *,
    target_variable: str | None,
    target_quantity_id: str | None,
) -> tuple[list[dict], list[str]]:
    normalized_steps: list[dict] = []
    notes: list[str] = []

    for step in graph_steps:
        normalized_step = dict(step)
        normalized_step["expression"] = _normalize_step_expression(step.get("expression"))
        normalized_inputs = [str(ref).strip() for ref in step.get("input_refs", []) if str(ref).strip()]
        normalized_output_ref = str(step.get("output_ref", "")).strip()
        if target_variable:
            normalized_inputs = [target_variable if ref == "target" else ref for ref in normalized_inputs]
            if normalized_output_ref == "target":
                normalized_output_ref = target_variable
        normalized_step["input_refs"] = normalized_inputs
        normalized_step["output_ref"] = normalized_output_ref
        normalized_steps.append(normalized_step)

    if not normalized_steps or not target_variable:
        return normalized_steps, notes

    produced_refs = [step.get("output_ref") for step in normalized_steps if step.get("output_ref")]
    if target_variable in produced_refs:
        return normalized_steps, notes

    last_output_ref = str(normalized_steps[-1].get("output_ref", "")).strip()
    if not last_output_ref:
        return normalized_steps, notes

    should_retarget = False
    if target_quantity_id and last_output_ref == target_quantity_id:
        should_retarget = True
    elif _looks_like_generated_quantity_id(last_output_ref):
        should_retarget = True

    if not should_retarget:
        return normalized_steps, notes

    for step in normalized_steps:
        if step.get("output_ref") == last_output_ref:
            step["output_ref"] = target_variable
        step["input_refs"] = [target_variable if ref == last_output_ref else ref for ref in step.get("input_refs", [])]
        expression = str(step.get("expression", "")).strip()
        if expression:
            step["expression"] = re.sub(rf"\b{re.escape(last_output_ref)}\b", target_variable, expression)

    notes.append(f"local_graph_repair:retargeted_output_ref:{last_output_ref}->{target_variable}")
    return normalized_steps, notes


def _build_target_payload_from_sketch(
    heuristic_problem: FormalizedProblem,
    payload: dict,
) -> dict:
    target_payload = heuristic_problem.target.model_dump(mode="json") if heuristic_problem.target is not None else {}
    target_block = payload.get("target")
    source = target_block if isinstance(target_block, dict) else None
    if isinstance(source, dict):
        target_payload.update(
            {
                key: value
                for key, value in source.items()
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
        )
    return target_payload


def _build_relation_candidates_from_sketch(
    heuristic_problem: FormalizedProblem,
    payload: dict,
    *,
    target_variable: str | None,
    quantities: list[QuantityAnnotation],
) -> list[RelationCandidate]:
    relation_block = payload.get("relation")
    raw_relations = []
    if isinstance(relation_block, dict):
        raw_relations = [relation_block]

    if raw_relations:
        relation_candidates: list[RelationCandidate] = []
        for index, raw_relation in enumerate(raw_relations, start=1):
            relation_payload = {
                "relation_id": raw_relation.get("relation_id") or f"relation_{index}",
                "relation_type": raw_relation.get("relation_type", RelationType.UNKNOWN.value),
                "operation_hint": raw_relation.get("operation_hint", OperationType.UNKNOWN.value),
                "source_quantity_ids": raw_relation.get("source_quantity_ids")
                or [quantity.quantity_id for quantity in quantities],
                "target_variable": raw_relation.get("target_variable") or target_variable,
                "expression": _normalize_relation_expression(raw_relation.get("expression")),
                "rationale": raw_relation.get("rationale"),
                "confidence": raw_relation.get("confidence", 0.75),
                "provenance": ProvenanceSource.LLM.value,
            }
            relation_candidates.append(RelationCandidate.model_validate(relation_payload))
        return relation_candidates

    return list(heuristic_problem.relation_candidates)


def _compile_quantities_from_semantic_sketch(
    heuristic_problem: FormalizedProblem,
    payload: dict,
    notes: list[str],
) -> list[QuantityAnnotation]:
    quantity_updates_by_id: dict[str, dict] = {}
    raw_quantity_annotations = payload.get("quantity_annotations")
    quantity_blocks = []
    if isinstance(raw_quantity_annotations, list):
        quantity_blocks = [item for item in raw_quantity_annotations if isinstance(item, dict)]

    for raw_update in quantity_blocks:
        quantity_id = str(raw_update.get("quantity_id", "")).strip()
        if not quantity_id:
            continue
        sanitized, invalid_note = _sanitize_quantity_update(raw_update)
        if invalid_note:
            notes.append(invalid_note)
        quantity_updates_by_id[quantity_id] = sanitized

    quantities: list[QuantityAnnotation] = []
    for quantity in heuristic_problem.quantities:
        update = quantity_updates_by_id.get(quantity.quantity_id, {})
        quantity_payload = quantity.model_dump(mode="json")
        quantity_payload.update(
            {
                key: value
                for key, value in update.items()
                if key in {"unit", "entity_id", "semantic_role", "is_target_candidate"}
            }
        )
        quantities.append(QuantityAnnotation.model_validate(quantity_payload))
        if update.get("semantic_role") and update.get("semantic_role") != quantity.semantic_role.value:
            notes.append(
                f"llm_quantity_role_update:{quantity.quantity_id}:{quantity.semantic_role.value}->{update.get('semantic_role')}"
            )

    existing_quantity_ids = {quantity.quantity_id for quantity in quantities}
    raw_semantic_facts = payload.get("semantic_facts")
    fact_blocks = []
    if isinstance(raw_semantic_facts, list):
        fact_blocks = [item for item in raw_semantic_facts if isinstance(item, dict)]

    for index, raw_fact in enumerate(fact_blocks, start=1):
        fact_notes = _coerce_list_of_strings(raw_fact.get("notes"))
        if raw_fact.get("grounding"):
            fact_notes.extend(_coerce_list_of_strings([raw_fact.get("grounding")]))
        latent_payload = {
            "quantity_id": str(raw_fact.get("fact_id", "")).strip()
            or str(raw_fact.get("quantity_id", "")).strip()
            or f"latent_quantity_{index}",
            "surface_text": raw_fact.get("label")
            or raw_fact.get("surface_text")
            or str(raw_fact.get("value", "")),
            "value": raw_fact.get("value"),
            "unit": raw_fact.get("unit"),
            "entity_id": raw_fact.get("entity_id"),
            "semantic_role": raw_fact.get("semantic_role", QuantitySemanticRole.INTERMEDIATE.value),
            "is_target_candidate": raw_fact.get("is_target_candidate", False),
            "notes": fact_notes,
        }
        latent_payload, latent_note = _sanitize_latent_quantity_payload(
            latent_payload,
            existing_quantity_ids=existing_quantity_ids,
        )
        if latent_note:
            notes.append(latent_note)
        if latent_payload is None:
            continue
        latent_payload["provenance"] = ProvenanceSource.LLM.value
        quantities.append(QuantityAnnotation.model_validate(latent_payload))
        existing_quantity_ids.add(latent_payload["quantity_id"])
        notes.append(f"llm_semantic_fact_added:{latent_payload['quantity_id']}")

    return quantities


def _extract_graph_steps_from_payload(payload: dict) -> list[dict]:
    plan_steps = payload.get("plan_steps")
    if isinstance(plan_steps, list):
        return [step for step in plan_steps if isinstance(step, dict)]
    return []


def _build_compact_draft(heuristic_problem: FormalizedProblem, evidence_pack: dict) -> dict:
    return {
        "problem_text": heuristic_problem.problem_text,
        "sentence_spans": list(evidence_pack.get("sentence_spans", [])),
        "numeric_mentions": list(evidence_pack.get("numeric_mentions", [])),
        "implicit_quantity_cues": list(evidence_pack.get("implicit_quantity_cues", [])),
        "lexical_cues": list(evidence_pack.get("lexical_cues", [])),
        "target_span_candidates": list(evidence_pack.get("target_span_candidates", [])),
        "target_link_candidates": list(evidence_pack.get("target_link_candidates", [])),
        "relation_candidates": list(evidence_pack.get("relation_candidates", [])),
        "entity_candidates": list(evidence_pack.get("entity_candidates", [])),
        "heuristic_projection": {
            "quantities": [
                {
                    "quantity_id": quantity.quantity_id,
                    "surface_text": quantity.surface_text,
                    "value": quantity.value,
                    "unit": quantity.unit,
                    "entity_id": quantity.entity_id,
                    "semantic_role": quantity.semantic_role.value,
                    "is_target_candidate": quantity.is_target_candidate,
                }
                for quantity in heuristic_problem.quantities
            ],
            "target": (
                {
                    "surface_text": heuristic_problem.target.surface_text,
                    "normalized_question": heuristic_problem.target.normalized_question,
                    "target_variable": heuristic_problem.target.target_variable,
                    "target_quantity_id": heuristic_problem.target.target_quantity_id,
                    "entity_id": heuristic_problem.target.entity_id,
                    "unit": heuristic_problem.target.unit,
                    "description": heuristic_problem.target.description,
                }
                if heuristic_problem.target is not None
                else None
            ),
            "relation_candidates": [
                {
                    "relation_id": relation.relation_id,
                    "relation_type": relation.relation_type.value,
                    "operation_hint": relation.operation_hint.value,
                    "source_quantity_ids": list(relation.source_quantity_ids),
                    "target_variable": relation.target_variable,
                    "expression": relation.expression,
                    "rationale": relation.rationale,
                }
                for relation in heuristic_problem.relation_candidates
            ],
        },
        "draft_notes": list(heuristic_problem.notes),
        "resolved_quantities": [
            {
                "quantity_id": quantity.quantity_id,
                "surface_text": quantity.surface_text,
                "value": quantity.value,
                "unit": quantity.unit,
                "entity_id": quantity.entity_id,
                "semantic_role": quantity.semantic_role.value,
                "is_target_candidate": quantity.is_target_candidate,
            }
            for quantity in heuristic_problem.quantities
        ],
        "resolved_entities": [
            {
                "entity_id": entity.entity_id,
                "surface_text": entity.surface_text,
                "normalized_name": entity.normalized_name,
                "entity_type": entity.entity_type,
            }
            for entity in heuristic_problem.entities
        ],
        "resolved_target": (
            {
                "surface_text": heuristic_problem.target.surface_text,
                "normalized_question": heuristic_problem.target.normalized_question,
                "target_variable": heuristic_problem.target.target_variable,
                "target_quantity_id": heuristic_problem.target.target_quantity_id,
                "entity_id": heuristic_problem.target.entity_id,
                "unit": heuristic_problem.target.unit,
                "description": heuristic_problem.target.description,
            }
            if heuristic_problem.target is not None
            else None
        ),
        "graph_steps": [
            {
                "step_id": node.step_id,
                "step_index": node.step_index,
                "operation": node.operation.value if node.operation is not None else None,
                "expression": node.expression,
                "label": node.label,
                "input_refs": [
                    edge.source_node_id
                    for edge in sorted(
                        (
                            edge
                            for edge in (heuristic_problem.problem_graph.edges if heuristic_problem.problem_graph else [])
                            if edge.edge_type == ProblemGraphEdgeType.INPUT_TO_OPERATION
                            and edge.target_node_id == node.node_id
                        ),
                        key=lambda edge: edge.position if edge.position is not None else 0,
                    )
                ],
                "output_ref": next(
                    (
                        edge.target_node_id
                        for edge in (heuristic_problem.problem_graph.edges if heuristic_problem.problem_graph else [])
                        if edge.edge_type == ProblemGraphEdgeType.OUTPUT_FROM_OPERATION
                        and edge.source_node_id == node.node_id
                    ),
                    None,
                ),
            }
            for node in (heuristic_problem.problem_graph.nodes if heuristic_problem.problem_graph else [])
            if node.node_type == ProblemGraphNodeType.OPERATION
        ],
        "graph_target_node_id": (
            heuristic_problem.problem_graph.target_node_id if heuristic_problem.problem_graph is not None else None
        ),
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
    quantities = _compile_quantities_from_semantic_sketch(heuristic_problem, payload, notes)
    existing_quantity_ids = {quantity.quantity_id for quantity in quantities}

    entities = list(heuristic_problem.entities)
    target_payload = _build_target_payload_from_sketch(heuristic_problem, payload)
    target_variable = str(target_payload.get("target_variable", "")).strip() or (
        heuristic_problem.target.target_variable if heuristic_problem.target is not None else ""
    )
    target_quantity_id = target_payload.get("target_quantity_id")
    if target_quantity_id is not None and target_quantity_id not in existing_quantity_ids:
        notes.append(f"local_target_repair:cleared_unknown_target_quantity_id:{target_quantity_id}")
        target_payload["target_quantity_id"] = None
    target_payload["provenance"] = ProvenanceSource.LLM.value
    target = TargetSpec.model_validate(target_payload) if target_payload else None

    relation_candidates = _build_relation_candidates_from_sketch(
        heuristic_problem,
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
