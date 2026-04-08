"""Build comparable graph artifacts from parsed student work."""
from __future__ import annotations

from src.models import (
    FormalizedProblem,
    ProblemGraph,
    ProblemGraphEdge,
    ProblemGraphEdgeType,
    ProblemGraphNode,
    ProblemGraphNodeType,
    ProvenanceSource,
    QuantitySemanticRole,
    StudentWorkState,
    TraceOperation,
)


def _graph_provenance(student_work: StudentWorkState) -> ProvenanceSource:
    if any("llm_student_parse_used" in note for note in student_work.notes):
        return ProvenanceSource.LLM
    return ProvenanceSource.HEURISTIC


def _target_variable(problem: FormalizedProblem | None) -> str | None:
    if problem is not None and problem.target is not None:
        return problem.target.target_variable
    return None


def _add_node_if_missing(
    nodes: dict[str, ProblemGraphNode],
    node: ProblemGraphNode,
) -> None:
    nodes.setdefault(node.node_id, node)


def _ensure_reference_node(
    ref_id: str,
    nodes: dict[str, ProblemGraphNode],
    problem: FormalizedProblem | None,
    student_work: StudentWorkState,
    provenance: ProvenanceSource,
) -> None:
    if ref_id in nodes:
        return

    semantic_fact = next((item for item in student_work.semantic_facts if item.fact_id == ref_id), None)
    if semantic_fact is not None:
        _add_node_if_missing(
            nodes,
            ProblemGraphNode(
                node_id=semantic_fact.fact_id,
                node_type=ProblemGraphNodeType.INTERMEDIATE,
                label=semantic_fact.label,
                value=semantic_fact.value,
                semantic_role=QuantitySemanticRole.INTERMEDIATE,
                confidence=semantic_fact.confidence,
                provenance=provenance,
                notes=list(semantic_fact.notes)
                + ([f"grounding={semantic_fact.grounding}"] if semantic_fact.grounding else []),
            ),
        )
        return

    if problem is not None:
        quantity = next((item for item in problem.quantities if item.quantity_id == ref_id), None)
        if quantity is not None:
            _add_node_if_missing(
                nodes,
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
                ),
            )
            return

    target_ref = _target_variable(problem)
    node_type = ProblemGraphNodeType.TARGET if ref_id == target_ref else ProblemGraphNodeType.INTERMEDIATE
    _add_node_if_missing(
        nodes,
        ProblemGraphNode(
            node_id=ref_id,
            node_type=node_type,
            label=ref_id,
            target_variable=ref_id if node_type == ProblemGraphNodeType.TARGET else None,
            semantic_role=QuantitySemanticRole.INTERMEDIATE if node_type == ProblemGraphNodeType.INTERMEDIATE else None,
            confidence=0.55,
            provenance=provenance,
            notes=["student_reference_placeholder"],
        ),
    )


def _append_edge(
    edges: list[ProblemGraphEdge],
    seen_ids: set[str],
    edge: ProblemGraphEdge,
) -> None:
    if edge.edge_id in seen_ids:
        return
    edges.append(edge)
    seen_ids.add(edge.edge_id)


def build_student_work_graph(
    student_work: StudentWorkState,
    problem: FormalizedProblem | None = None,
    provenance_override: ProvenanceSource | None = None,
) -> ProblemGraph | None:
    """Construct a comparable graph representation for student work."""
    has_structured_step = any(
        step.extracted_value is not None or (step.operation is not None and step.operation != TraceOperation.UNKNOWN)
        for step in student_work.steps
    )
    if student_work.normalized_final_answer is None and not has_structured_step:
        return None

    provenance = provenance_override or _graph_provenance(student_work)
    nodes: dict[str, ProblemGraphNode] = {}
    edges: list[ProblemGraphEdge] = []
    edge_ids: set[str] = set()
    output_node_ids: list[str] = []
    value_sources: list[tuple[str, float]] = []
    output_node_to_step: dict[str, str] = {}

    for semantic_fact in student_work.semantic_facts:
        _ensure_reference_node(semantic_fact.fact_id, nodes, problem, student_work, provenance)

    for step in student_work.steps:
        for ref_id in step.referenced_ids:
            _ensure_reference_node(ref_id, nodes, problem, student_work, provenance)

        operation = step.operation
        if operation is None:
            continue

        op_node_id = f"student_op_{step.step_id}"
        _add_node_if_missing(
            nodes,
            ProblemGraphNode(
                node_id=op_node_id,
                node_type=ProblemGraphNodeType.OPERATION,
                label=step.raw_text or step.step_id,
                operation=operation,
                expression=step.raw_text,
                step_id=step.step_id,
                step_index=int(step.step_id.split("_")[-1]) if step.step_id.split("_")[-1].isdigit() else len(output_node_ids) + 1,
                confidence=step.confidence,
                provenance=provenance,
                notes=list(step.notes),
            ),
        )

        input_refs_for_graph: list[str] = list(step.referenced_ids)
        for input_value in step.input_values:
            matched_source = next(
                (
                    source_node_id
                    for source_node_id, source_value in reversed(value_sources)
                    if abs(source_value - input_value) < 1e-9 and source_node_id not in input_refs_for_graph
                ),
                None,
            )
            if matched_source is not None:
                input_refs_for_graph.append(matched_source)

        for position, ref_id in enumerate(input_refs_for_graph):
            _append_edge(
                edges,
                edge_ids,
                ProblemGraphEdge(
                    edge_id=f"edge_{ref_id}_to_{op_node_id}_{position}",
                    source_node_id=ref_id,
                    target_node_id=op_node_id,
                    edge_type=ProblemGraphEdgeType.INPUT_TO_OPERATION,
                    position=position,
                    confidence=step.confidence,
                    provenance=provenance,
                    notes=[],
                ),
            )

        if step.extracted_value is None:
            continue

        output_node_id = f"student_output_{step.step_id}"
        output_notes = list(step.notes)
        _add_node_if_missing(
            nodes,
            ProblemGraphNode(
                node_id=output_node_id,
                node_type=ProblemGraphNodeType.INTERMEDIATE,
                label=output_node_id,
                value=step.extracted_value,
                semantic_role=QuantitySemanticRole.INTERMEDIATE,
                confidence=step.confidence,
                provenance=provenance,
                notes=output_notes,
            ),
        )
        output_node_ids.append(output_node_id)
        output_node_to_step[output_node_id] = step.step_id
        value_sources.append((output_node_id, step.extracted_value))
        _append_edge(
            edges,
            edge_ids,
            ProblemGraphEdge(
                edge_id=f"edge_{op_node_id}_to_{output_node_id}",
                source_node_id=op_node_id,
                target_node_id=output_node_id,
                edge_type=ProblemGraphEdgeType.OUTPUT_FROM_OPERATION,
                confidence=step.confidence,
                provenance=provenance,
                notes=[],
            ),
        )

    target_node_id = None
    if student_work.normalized_final_answer is not None:
        target_node_id = "student_final_answer"
        target_notes = []
        if student_work.selected_target_ref is not None:
            target_notes.append(f"selected_target_ref={student_work.selected_target_ref}")
            _ensure_reference_node(student_work.selected_target_ref, nodes, problem, student_work, provenance)
        _add_node_if_missing(
            nodes,
            ProblemGraphNode(
                node_id=target_node_id,
                node_type=ProblemGraphNodeType.TARGET,
                label="student_final_answer",
                value=student_work.normalized_final_answer,
                target_variable=student_work.selected_target_ref or "student_final_answer",
                confidence=min(max(student_work.confidence, 0.4), 0.99),
                provenance=provenance,
                notes=target_notes,
            ),
        )

        matching_output_candidates = [
            output_node_id
            for output_node_id, output_value in value_sources
            if abs(output_value - student_work.normalized_final_answer) < 1e-9
        ]
        matching_output_id = None
        for output_node_id in reversed(matching_output_candidates):
            step_id = output_node_to_step.get(output_node_id)
            step = next((candidate for candidate in student_work.steps if candidate.step_id == step_id), None)
            if step is not None and "answer" in step.raw_text.lower() and step.operation in {TraceOperation.DERIVE, TraceOperation.UNKNOWN}:
                continue
            matching_output_id = output_node_id
            break
        if matching_output_id is None and matching_output_candidates:
            matching_output_id = matching_output_candidates[-1]

        if student_work.selected_target_ref is not None:
            _append_edge(
                edges,
                edge_ids,
                ProblemGraphEdge(
                    edge_id=f"edge_{student_work.selected_target_ref}_to_{target_node_id}",
                    source_node_id=student_work.selected_target_ref,
                    target_node_id=target_node_id,
                    edge_type=ProblemGraphEdgeType.TARGETS_VALUE,
                    confidence=min(max(student_work.confidence, 0.4), 0.99),
                    provenance=provenance,
                    notes=["linked_from_selected_target_ref"],
                ),
            )

        if matching_output_id is not None:
            _append_edge(
                edges,
                edge_ids,
                ProblemGraphEdge(
                    edge_id=f"edge_{matching_output_id}_to_{target_node_id}",
                    source_node_id=matching_output_id,
                    target_node_id=target_node_id,
                    edge_type=ProblemGraphEdgeType.TARGETS_VALUE,
                    confidence=min(max(student_work.confidence, 0.4), 0.99),
                    provenance=provenance,
                    notes=["linked_from_matching_final_value"],
                ),
            )
    elif output_node_ids:
        target_node_id = output_node_ids[-1]

    graph_notes = [f"student_steps={len(student_work.steps)}", "student_graph_built"]
    if student_work.semantic_facts:
        graph_notes.append(f"student_semantic_facts={len(student_work.semantic_facts)}")
    if student_work.selected_target_ref is not None:
        graph_notes.append(f"selected_target_ref={student_work.selected_target_ref}")

    return ProblemGraph(
        nodes=list(nodes.values()),
        edges=edges,
        target_node_id=target_node_id,
        confidence=min(max(student_work.confidence, 0.35), 0.98),
        provenance=provenance,
        notes=graph_notes,
    )
