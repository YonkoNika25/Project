"""Problem graph construction from a structured formalized problem."""
from __future__ import annotations

from src.models import (
    FormalizedProblem,
    ProblemGraph,
    ProblemGraphEdge,
    ProblemGraphEdgeType,
    ProblemGraphNode,
    ProblemGraphNodeType,
    ProvenanceSource,
    QuantityAnnotation,
    QuantitySemanticRole,
    RelationType,
    TraceOperation,
)


def _first_quantity_with_role(
    quantities: list[QuantityAnnotation],
    role: QuantitySemanticRole,
) -> QuantityAnnotation | None:
    return next((quantity for quantity in quantities if quantity.semantic_role == role), None)


def _quantity_has_role_hint(quantity: QuantityAnnotation, hint: str) -> bool:
    return any(note == f"role_hints={hint}" or f",{hint}" in note or note.endswith(f"={hint}") for note in quantity.notes)


def _quantity_has_unit_candidate(quantity: QuantityAnnotation, candidate: str) -> bool:
    normalized = candidate.strip().lower()
    if not normalized:
        return False
    return any(
        note.startswith("unit_candidates=")
        and normalized in {item.strip().lower() for item in note.split("=", 1)[-1].split(",") if item.strip()}
        for note in quantity.notes
    )


def _resolved_relation(problem: FormalizedProblem):
    # Heuristic relation candidates are accepted only when they are confident and not ambiguous.
    if not problem.relation_candidates:
        return None
    primary = problem.relation_candidates[0]
    if primary.provenance != ProvenanceSource.HEURISTIC:
        return primary
    if primary.relation_type == RelationType.UNKNOWN or primary.confidence < 0.55:
        return None
    if len(problem.relation_candidates) > 1:
        runner_up = problem.relation_candidates[1]
        if runner_up.confidence >= primary.confidence - 0.1:
            return None
    return primary


def _base_quantities(quantities: list[QuantityAnnotation]) -> list[QuantityAnnotation]:
    return [quantity for quantity in quantities if quantity.semantic_role == QuantitySemanticRole.BASE]


def _select_rate_unit_price_quantity(problem: FormalizedProblem) -> QuantityAnnotation | None:
    target_unit = problem.target.unit if problem.target is not None else None
    candidates = [
        quantity
        for quantity in problem.quantities
        if quantity.semantic_role == QuantitySemanticRole.UNIT_RATE
        or _quantity_has_role_hint(quantity, "rate_like")
        or "$" in quantity.surface_text
    ]
    if not candidates:
        return None
    if target_unit is not None:
        match = next((quantity for quantity in candidates if quantity.unit == target_unit), None)
        if match is not None:
            return match
    return next((quantity for quantity in candidates if "$" in quantity.surface_text), candidates[0])


def _select_rate_unit_base_quantity(problem: FormalizedProblem) -> QuantityAnnotation | None:
    target_unit = problem.target.unit if problem.target is not None else None
    base_candidates = _base_quantities(problem.quantities)
    if base_candidates:
        return base_candidates[0]

    for quantity in problem.quantities:
        if (
            quantity.semantic_role in (QuantitySemanticRole.PERCENT, QuantitySemanticRole.THRESHOLD)
            or _quantity_has_role_hint(quantity, "percent_like")
            or _quantity_has_role_hint(quantity, "threshold_like")
            or "$" in quantity.surface_text
            or "%" in quantity.surface_text
        ):
            continue
        if target_unit is not None and quantity.unit == target_unit:
            continue
        return quantity

    return next(
        (
            quantity
            for quantity in problem.quantities
            if quantity.semantic_role != QuantitySemanticRole.PERCENT
        ),
        None,
    )


def _target_ref(problem: FormalizedProblem) -> str:
    if problem.target is not None:
        return problem.target.target_variable
    return "answer"


def _add_node(
    nodes: list[ProblemGraphNode],
    seen_node_ids: set[str],
    node: ProblemGraphNode,
) -> None:
    if node.node_id in seen_node_ids:
        return
    nodes.append(node)
    seen_node_ids.add(node.node_id)


def _add_edge(
    edges: list[ProblemGraphEdge],
    seen_edge_ids: set[str],
    edge: ProblemGraphEdge,
) -> None:
    if edge.edge_id in seen_edge_ids:
        return
    edges.append(edge)
    seen_edge_ids.add(edge.edge_id)


def _build_base_graph(problem: FormalizedProblem) -> tuple[list[ProblemGraphNode], list[ProblemGraphEdge], set[str], set[str]]:
    nodes: list[ProblemGraphNode] = []
    edges: list[ProblemGraphEdge] = []
    seen_node_ids: set[str] = set()
    seen_edge_ids: set[str] = set()

    for entity in problem.entities:
        _add_node(
            nodes,
            seen_node_ids,
            ProblemGraphNode(
                node_id=entity.entity_id,
                node_type=ProblemGraphNodeType.ENTITY,
                label=entity.surface_text,
                entity_id=entity.entity_id,
                confidence=0.95,
                provenance=ProvenanceSource.PROBLEM_TEXT,
            ),
        )

    for quantity in problem.quantities:
        _add_node(
            nodes,
            seen_node_ids,
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
        if quantity.entity_id is not None:
            _add_edge(
                edges,
                seen_edge_ids,
                ProblemGraphEdge(
                    edge_id=f"edge_{quantity.entity_id}_owns_{quantity.quantity_id}",
                    source_node_id=quantity.entity_id,
                    target_node_id=quantity.quantity_id,
                    edge_type=ProblemGraphEdgeType.ENTITY_HAS_QUANTITY,
                    confidence=0.9,
                    provenance=ProvenanceSource.PROBLEM_TEXT,
                ),
            )

    if problem.target is not None:
        _add_node(
            nodes,
            seen_node_ids,
            ProblemGraphNode(
                node_id=problem.target.target_variable,
                node_type=ProblemGraphNodeType.TARGET,
                label=problem.target.surface_text,
                unit=problem.target.unit,
                target_variable=problem.target.target_variable,
                entity_id=problem.target.entity_id,
                confidence=problem.target.confidence,
                provenance=problem.target.provenance,
            ),
        )
        if problem.target.entity_id is not None:
            _add_edge(
                edges,
                seen_edge_ids,
                ProblemGraphEdge(
                    edge_id=f"edge_{problem.target.target_variable}_describes_{problem.target.entity_id}",
                    source_node_id=problem.target.target_variable,
                    target_node_id=problem.target.entity_id,
                    edge_type=ProblemGraphEdgeType.DESCRIBES_ENTITY,
                    confidence=0.82,
                    provenance=problem.target.provenance,
                ),
            )

    return nodes, edges, seen_node_ids, seen_edge_ids


def _ensure_value_node(
    nodes: list[ProblemGraphNode],
    seen_node_ids: set[str],
    node_id: str,
    node_type: ProblemGraphNodeType,
    label: str,
    unit: str | None,
    confidence: float,
    provenance: ProvenanceSource,
) -> None:
    _add_node(
        nodes,
        seen_node_ids,
        ProblemGraphNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            unit=unit,
            target_variable=node_id if node_type == ProblemGraphNodeType.TARGET else None,
            confidence=confidence,
            provenance=provenance,
        ),
    )


def _add_operation(
    nodes: list[ProblemGraphNode],
    edges: list[ProblemGraphEdge],
    seen_node_ids: set[str],
    seen_edge_ids: set[str],
    *,
    step_id: str,
    step_index: int,
    operation: TraceOperation,
    expression: str,
    input_refs: list[str],
    output_ref: str,
    explanation: str,
    output_type: ProblemGraphNodeType,
    output_unit: str | None,
    confidence: float,
    provenance: ProvenanceSource,
) -> None:
    op_node_id = f"op_{step_id}"
    _add_node(
        nodes,
        seen_node_ids,
        ProblemGraphNode(
            node_id=op_node_id,
            node_type=ProblemGraphNodeType.OPERATION,
            label=explanation,
            operation=operation,
            expression=expression,
            step_id=step_id,
            step_index=step_index,
            confidence=confidence,
            provenance=provenance,
        ),
    )
    _ensure_value_node(
        nodes,
        seen_node_ids,
        node_id=output_ref,
        node_type=output_type,
        label=output_ref,
        unit=output_unit,
        confidence=confidence,
        provenance=provenance,
    )

    for position, input_ref in enumerate(input_refs):
        _add_edge(
            edges,
            seen_edge_ids,
            ProblemGraphEdge(
                edge_id=f"edge_{input_ref}_to_{op_node_id}_{position}",
                source_node_id=input_ref,
                target_node_id=op_node_id,
                edge_type=ProblemGraphEdgeType.INPUT_TO_OPERATION,
                position=position,
                confidence=confidence,
                provenance=provenance,
            ),
        )

    _add_edge(
        edges,
        seen_edge_ids,
        ProblemGraphEdge(
            edge_id=f"edge_{op_node_id}_to_{output_ref}",
            source_node_id=op_node_id,
            target_node_id=output_ref,
            edge_type=ProblemGraphEdgeType.OUTPUT_FROM_OPERATION,
            confidence=confidence,
            provenance=provenance,
        ),
    )


def _add_rate_subgraph(
    problem: FormalizedProblem,
    nodes: list[ProblemGraphNode],
    edges: list[ProblemGraphEdge],
    seen_node_ids: set[str],
    seen_edge_ids: set[str],
    notes: list[str],
) -> None:
    unit_rate = _select_rate_unit_price_quantity(problem)
    percent = _first_quantity_with_role(problem.quantities, QuantitySemanticRole.PERCENT) or next(
        (quantity for quantity in problem.quantities if _quantity_has_role_hint(quantity, "percent_like") or "%" in quantity.surface_text),
        None,
    )
    threshold = _first_quantity_with_role(problem.quantities, QuantitySemanticRole.THRESHOLD) or next(
        (quantity for quantity in problem.quantities if _quantity_has_role_hint(quantity, "threshold_like")),
        None,
    )
    base = _select_rate_unit_base_quantity(problem)
    target_ref = _target_ref(problem)
    target_unit = problem.target.unit if problem.target is not None else None

    if not all((unit_rate, percent, threshold, base)):
        notes.append("graph_rate_relation_missing_components")
        return

    _add_operation(
        nodes,
        edges,
        seen_node_ids,
        seen_edge_ids,
        step_id="step_1_excess_quantity",
        step_index=1,
        operation=TraceOperation.SUBTRACT,
        expression=f"max({base.quantity_id} - {threshold.quantity_id}, 0)",
        input_refs=[base.quantity_id, threshold.quantity_id],
        output_ref="excess_quantity",
        explanation="Find how many units are beyond the discount threshold.",
        output_type=ProblemGraphNodeType.INTERMEDIATE,
        output_unit=base.unit,
        confidence=0.94,
        provenance=ProvenanceSource.HEURISTIC,
    )
    _add_operation(
        nodes,
        edges,
        seen_node_ids,
        seen_edge_ids,
        step_id="step_2_discount_per_unit",
        step_index=2,
        operation=TraceOperation.PERCENT_OF,
        expression=f"({percent.quantity_id} / 100) * {unit_rate.quantity_id}",
        input_refs=[percent.quantity_id, unit_rate.quantity_id],
        output_ref="discount_per_unit",
        explanation="Compute the discount value applied to each discounted unit.",
        output_type=ProblemGraphNodeType.INTERMEDIATE,
        output_unit=target_unit,
        confidence=0.93,
        provenance=ProvenanceSource.HEURISTIC,
    )
    _add_operation(
        nodes,
        edges,
        seen_node_ids,
        seen_edge_ids,
        step_id="step_3_total_discount",
        step_index=3,
        operation=TraceOperation.MULTIPLY,
        expression="excess_quantity * discount_per_unit",
        input_refs=["excess_quantity", "discount_per_unit"],
        output_ref="total_discount",
        explanation="Multiply discounted units by the discount per unit.",
        output_type=ProblemGraphNodeType.INTERMEDIATE,
        output_unit=target_unit,
        confidence=0.93,
        provenance=ProvenanceSource.HEURISTIC,
    )
    _add_operation(
        nodes,
        edges,
        seen_node_ids,
        seen_edge_ids,
        step_id="step_4_gross_total",
        step_index=4,
        operation=TraceOperation.MULTIPLY,
        expression=f"{base.quantity_id} * {unit_rate.quantity_id}",
        input_refs=[base.quantity_id, unit_rate.quantity_id],
        output_ref="gross_total",
        explanation="Compute the total before any discount.",
        output_type=ProblemGraphNodeType.INTERMEDIATE,
        output_unit=target_unit,
        confidence=0.94,
        provenance=ProvenanceSource.HEURISTIC,
    )
    _add_operation(
        nodes,
        edges,
        seen_node_ids,
        seen_edge_ids,
        step_id="step_5_final_total",
        step_index=5,
        operation=TraceOperation.SUBTRACT,
        expression="gross_total - total_discount",
        input_refs=["gross_total", "total_discount"],
        output_ref=target_ref,
        explanation="Subtract the total discount from the gross total.",
        output_type=ProblemGraphNodeType.TARGET,
        output_unit=target_unit,
        confidence=0.95,
        provenance=ProvenanceSource.HEURISTIC,
    )
    notes.append("graph_built_from_rate_relation")


def _add_single_step_subgraph(
    problem: FormalizedProblem,
    nodes: list[ProblemGraphNode],
    edges: list[ProblemGraphEdge],
    seen_node_ids: set[str],
    seen_edge_ids: set[str],
    *,
    relation_type: RelationType,
    notes: list[str],
) -> None:
    target_ref = _target_ref(problem)
    target_unit = problem.target.unit if problem.target is not None else None
    quantity_refs = [quantity.quantity_id for quantity in problem.quantities]
    if not quantity_refs:
        notes.append("graph_missing_quantity_nodes")
        return

    if relation_type == RelationType.ADDITIVE_COMPOSITION:
        operation = TraceOperation.ADD
        expression = " + ".join(quantity_refs)
        explanation = "Add the relevant quantities to obtain the target."
        note = "graph_built_from_additive_relation"
        step_id = "step_1_add_all"
    elif relation_type == RelationType.SUBTRACTIVE_COMPARISON:
        operation = TraceOperation.SUBTRACT
        expression = quantity_refs[0] if len(quantity_refs) == 1 else f"{quantity_refs[0]} - " + " - ".join(quantity_refs[1:])
        explanation = "Subtract the removed or compared quantities from the base quantity."
        note = "graph_built_from_subtractive_relation"
        step_id = "step_1_subtract"
    elif relation_type == RelationType.MULTIPLICATIVE_SCALING:
        operation = TraceOperation.MULTIPLY
        expression = " * ".join(quantity_refs[:2]) if len(quantity_refs) >= 2 else quantity_refs[0]
        explanation = "Multiply the relevant factors to obtain the target."
        note = "graph_built_from_multiplicative_relation"
        step_id = "step_1_multiply"
    elif relation_type == RelationType.PARTITION_GROUPING:
        operation = TraceOperation.DIVIDE
        expression = f"{quantity_refs[0]} / {quantity_refs[1]}" if len(quantity_refs) >= 2 else quantity_refs[0]
        explanation = "Divide the total by the group count or group size."
        note = "graph_built_from_partition_relation"
        step_id = "step_1_divide"
    else:
        notes.append("graph_unknown_relation_type")
        return

    _add_operation(
        nodes,
        edges,
        seen_node_ids,
        seen_edge_ids,
        step_id=step_id,
        step_index=1,
        operation=operation,
        expression=expression,
        input_refs=quantity_refs if relation_type != RelationType.MULTIPLICATIVE_SCALING else quantity_refs[:2],
        output_ref=target_ref,
        explanation=explanation,
        output_type=ProblemGraphNodeType.TARGET,
        output_unit=target_unit,
        confidence=0.9,
        provenance=ProvenanceSource.HEURISTIC,
    )
    notes.append(note)


def _add_expression_fallback_subgraph(
    problem: FormalizedProblem,
    nodes: list[ProblemGraphNode],
    edges: list[ProblemGraphEdge],
    seen_node_ids: set[str],
    seen_edge_ids: set[str],
    notes: list[str],
) -> None:
    relation = problem.relation_candidates[0] if problem.relation_candidates else None
    if relation is None or relation.expression is None:
        notes.append("graph_missing_relation_expression")
        return

    lowered = relation.expression.lower()
    if "unresolved_relation(" in lowered or "rate_or_percent_relation(" in lowered:
        notes.append("graph_placeholder_relation_expression")
        return

    rhs = relation.expression.split("=", 1)[-1].strip()
    target_ref = _target_ref(problem)
    target_unit = problem.target.unit if problem.target is not None else None
    _add_operation(
        nodes,
        edges,
        seen_node_ids,
        seen_edge_ids,
        step_id="step_1_relation_expression",
        step_index=1,
        operation=TraceOperation.DERIVE,
        expression=rhs,
        input_refs=list(relation.source_quantity_ids),
        output_ref=target_ref,
        explanation="Use the relation expression provided by the formalizer.",
        output_type=ProblemGraphNodeType.TARGET,
        output_unit=target_unit,
        confidence=max(relation.confidence - 0.1, 0.35),
        provenance=relation.provenance,
    )
    notes.append("graph_built_from_relation_expression")


def build_problem_graph(problem: FormalizedProblem) -> ProblemGraph:
    """Build a typed problem graph from the current structured formalization."""
    nodes, edges, seen_node_ids, seen_edge_ids = _build_base_graph(problem)
    notes: list[str] = []

    if problem.provenance == ProvenanceSource.HEURISTIC:
        notes.append("graph_semantic_resolution_from_candidates")

    relation = _resolved_relation(problem)
    relation_type = relation.relation_type if relation is not None else RelationType.UNKNOWN

    # Route to the matching graph template by relation family.
    if relation_type == RelationType.RATE_UNIT_RELATION:
        _add_rate_subgraph(problem, nodes, edges, seen_node_ids, seen_edge_ids, notes)
    elif relation_type in (
        RelationType.ADDITIVE_COMPOSITION,
        RelationType.SUBTRACTIVE_COMPARISON,
        RelationType.MULTIPLICATIVE_SCALING,
        RelationType.PARTITION_GROUPING,
    ):
        _add_single_step_subgraph(
            problem,
            nodes,
            edges,
            seen_node_ids,
            seen_edge_ids,
            relation_type=relation_type,
            notes=notes,
        )
    else:
        # Last-resort path: try using relation.expression as a derivation step.
        _add_expression_fallback_subgraph(problem, nodes, edges, seen_node_ids, seen_edge_ids, notes)

    confidence = 0.35 if not any(node.node_type == ProblemGraphNodeType.OPERATION for node in nodes) else 0.9
    return ProblemGraph(
        nodes=nodes,
        edges=edges,
        target_node_id=_target_ref(problem) if problem.target is not None else None,
        confidence=max(min(problem.confidence, 0.98), confidence),
        provenance=problem.provenance if problem.provenance != ProvenanceSource.UNKNOWN else ProvenanceSource.HEURISTIC,
        notes=notes,
    )
