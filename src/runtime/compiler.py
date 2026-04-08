"""Compile structured math plans from a formalized problem."""
from __future__ import annotations

from typing import Iterable

from src.models import (
    ExecutablePlan,
    ExecutableStep,
    FormalizedProblem,
    ProblemGraphEdgeType,
    ProblemGraphNodeType,
    ProvenanceSource,
    QuantityAnnotation,
    QuantitySemanticRole,
    RelationCandidate,
    RelationType,
    TraceOperation,
)
from src.runtime.graph_validator import validate_problem_graph


def _first_quantity_with_role(
    quantities: Iterable[QuantityAnnotation],
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


def _resolved_relation(problem: FormalizedProblem) -> RelationCandidate | None:
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


def _base_quantities(quantities: Iterable[QuantityAnnotation]) -> list[QuantityAnnotation]:
    return [quantity for quantity in quantities if quantity.semantic_role == QuantitySemanticRole.BASE]


def _is_placeholder_expression(expression: str | None) -> bool:
    if not expression:
        return True
    lowered = expression.lower()
    return "unresolved_relation(" in lowered or "rate_or_percent_relation(" in lowered


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


def _compile_problem_graph_plan(problem: FormalizedProblem) -> ExecutablePlan | None:
    graph = problem.problem_graph
    if graph is None:
        return None

    validation = validate_problem_graph(problem)
    if not validation.is_valid:
        return None

    nodes_by_id = {node.node_id: node for node in graph.nodes}
    operation_nodes = sorted(
        (
            node
            for node in graph.nodes
            if node.node_type == ProblemGraphNodeType.OPERATION and node.step_index is not None
        ),
        key=lambda node: node.step_index or 0,
    )
    if not operation_nodes:
        return None

    steps: list[ExecutableStep] = []
    for node in operation_nodes:
        input_edges = sorted(
            (
                edge
                for edge in graph.edges
                if edge.edge_type == ProblemGraphEdgeType.INPUT_TO_OPERATION and edge.target_node_id == node.node_id
            ),
            key=lambda edge: edge.position if edge.position is not None else 999,
        )
        output_edge = next(
            (
                edge
                for edge in graph.edges
                if edge.edge_type == ProblemGraphEdgeType.OUTPUT_FROM_OPERATION and edge.source_node_id == node.node_id
            ),
            None,
        )
        if output_edge is None:
            return None

        input_refs: list[str] = []
        for edge in input_edges:
            source_node = nodes_by_id[edge.source_node_id]
            input_refs.append(source_node.quantity_id or source_node.target_variable or source_node.node_id)

        output_node = nodes_by_id[output_edge.target_node_id]
        output_ref = output_node.target_variable or output_node.node_id

        steps.append(
            ExecutableStep(
                step_id=node.step_id or node.node_id,
                operation=node.operation or TraceOperation.UNKNOWN,
                expression=node.expression or node.label,
                input_refs=input_refs,
                output_ref=output_ref,
                explanation=node.label,
                confidence=node.confidence,
                provenance=node.provenance,
            )
        )

    confidence = sum(step.confidence for step in steps) / len(steps)
    return ExecutablePlan(
        plan_id="plan_problem_graph",
        target_ref=graph.target_node_id or _target_ref(problem),
        steps=steps,
        assumptions=list(problem.assumptions),
        confidence=min(max(confidence, graph.confidence), 0.98),
        provenance=graph.provenance if graph.provenance != ProvenanceSource.UNKNOWN else ProvenanceSource.HEURISTIC,
        notes=["compiled_from_problem_graph"] + list(graph.notes),
    )


def _compile_rate_plan(problem: FormalizedProblem, relation: RelationCandidate) -> ExecutablePlan:
    quantities = list(problem.quantities)
    target_ref = _target_ref(problem)
    unit_rate = _select_rate_unit_price_quantity(problem)
    percent = _first_quantity_with_role(quantities, QuantitySemanticRole.PERCENT) or next(
        (quantity for quantity in quantities if _quantity_has_role_hint(quantity, "percent_like") or "%" in quantity.surface_text),
        None,
    )
    threshold = _first_quantity_with_role(quantities, QuantitySemanticRole.THRESHOLD) or next(
        (quantity for quantity in quantities if _quantity_has_role_hint(quantity, "threshold_like")),
        None,
    )
    base = _select_rate_unit_base_quantity(problem)

    notes = ["compiled_from_rate_unit_relation"]
    steps: list[ExecutableStep] = []

    if unit_rate and percent and threshold and base:
        steps.extend(
            [
                ExecutableStep(
                    step_id="step_1_excess_quantity",
                    operation=TraceOperation.SUBTRACT,
                    expression=f"max({base.quantity_id} - {threshold.quantity_id}, 0)",
                    input_refs=[base.quantity_id, threshold.quantity_id],
                    output_ref="excess_quantity",
                    explanation="Find how many units are beyond the discount threshold.",
                    confidence=0.94,
                    provenance=ProvenanceSource.HEURISTIC,
                ),
                ExecutableStep(
                    step_id="step_2_discount_per_unit",
                    operation=TraceOperation.PERCENT_OF,
                    expression=f"({percent.quantity_id} / 100) * {unit_rate.quantity_id}",
                    input_refs=[percent.quantity_id, unit_rate.quantity_id],
                    output_ref="discount_per_unit",
                    explanation="Compute the discount value applied to each discounted unit.",
                    confidence=0.93,
                    provenance=ProvenanceSource.HEURISTIC,
                ),
                ExecutableStep(
                    step_id="step_3_total_discount",
                    operation=TraceOperation.MULTIPLY,
                    expression="excess_quantity * discount_per_unit",
                    input_refs=["excess_quantity", "discount_per_unit"],
                    output_ref="total_discount",
                    explanation="Multiply discounted units by the discount per unit.",
                    confidence=0.93,
                    provenance=ProvenanceSource.HEURISTIC,
                ),
                ExecutableStep(
                    step_id="step_4_gross_total",
                    operation=TraceOperation.MULTIPLY,
                    expression=f"{base.quantity_id} * {unit_rate.quantity_id}",
                    input_refs=[base.quantity_id, unit_rate.quantity_id],
                    output_ref="gross_total",
                    explanation="Compute the total before any discount.",
                    confidence=0.94,
                    provenance=ProvenanceSource.HEURISTIC,
                ),
                ExecutableStep(
                    step_id="step_5_final_total",
                    operation=TraceOperation.SUBTRACT,
                    expression="gross_total - total_discount",
                    input_refs=["gross_total", "total_discount"],
                    output_ref=target_ref,
                    explanation="Subtract the total discount from the gross total.",
                    confidence=0.95,
                    provenance=ProvenanceSource.HEURISTIC,
                ),
            ]
        )
    elif relation.expression and not _is_placeholder_expression(relation.expression):
        rhs = relation.expression.split("=", 1)[-1].strip()
        steps.append(
            ExecutableStep(
                step_id="step_1_relation_fallback",
                operation=TraceOperation.DERIVE,
                expression=rhs,
                input_refs=list(relation.source_quantity_ids),
                output_ref=target_ref,
                explanation="Fallback relation execution for rate/unit relation.",
                confidence=0.45,
                provenance=ProvenanceSource.HEURISTIC,
            )
        )
        notes.append("rate_relation_fallback_expression")
    else:
        notes.append("rate_relation_missing_components")

    return ExecutablePlan(
        plan_id="plan_rate_unit_relation",
        target_ref=target_ref,
        steps=steps,
        assumptions=list(problem.assumptions),
        confidence=0.92 if steps else 0.2,
        provenance=ProvenanceSource.HEURISTIC,
        notes=notes,
    )


def _compile_additive_plan(problem: FormalizedProblem) -> ExecutablePlan:
    quantities = list(problem.quantities)
    target_ref = _target_ref(problem)
    terms = [quantity.quantity_id for quantity in quantities]
    expression = " + ".join(terms) if terms else "0"
    return ExecutablePlan(
        plan_id="plan_additive_composition",
        target_ref=target_ref,
        steps=[
            ExecutableStep(
                step_id="step_1_add_all",
                operation=TraceOperation.ADD,
                expression=expression,
                input_refs=terms,
                output_ref=target_ref,
                explanation="Add the relevant quantities to obtain the target.",
                confidence=0.9 if len(terms) >= 2 else 0.4,
                provenance=ProvenanceSource.HEURISTIC,
            )
        ],
        assumptions=list(problem.assumptions),
        confidence=0.88 if len(terms) >= 2 else 0.35,
        provenance=ProvenanceSource.HEURISTIC,
        notes=["compiled_from_additive_relation"],
    )


def _compile_subtractive_plan(problem: FormalizedProblem) -> ExecutablePlan:
    quantities = list(problem.quantities)
    target_ref = _target_ref(problem)
    refs = [quantity.quantity_id for quantity in quantities]
    if not refs:
        expression = "0"
    elif len(refs) == 1:
        expression = refs[0]
    else:
        expression = f"{refs[0]} - " + " - ".join(refs[1:])
    return ExecutablePlan(
        plan_id="plan_subtractive_comparison",
        target_ref=target_ref,
        steps=[
            ExecutableStep(
                step_id="step_1_subtract",
                operation=TraceOperation.SUBTRACT,
                expression=expression,
                input_refs=refs,
                output_ref=target_ref,
                explanation="Subtract the removed or compared quantities from the base quantity.",
                confidence=0.9 if len(refs) >= 2 else 0.4,
                provenance=ProvenanceSource.HEURISTIC,
            )
        ],
        assumptions=list(problem.assumptions),
        confidence=0.88 if len(refs) >= 2 else 0.35,
        provenance=ProvenanceSource.HEURISTIC,
        notes=["compiled_from_subtractive_relation"],
    )


def _compile_multiplicative_plan(problem: FormalizedProblem) -> ExecutablePlan:
    quantities = list(problem.quantities)
    target_ref = _target_ref(problem)
    refs = [quantity.quantity_id for quantity in quantities[:2]]
    expression = " * ".join(refs) if refs else "0"
    return ExecutablePlan(
        plan_id="plan_multiplicative_scaling",
        target_ref=target_ref,
        steps=[
            ExecutableStep(
                step_id="step_1_multiply",
                operation=TraceOperation.MULTIPLY,
                expression=expression,
                input_refs=refs,
                output_ref=target_ref,
                explanation="Multiply the relevant factors to obtain the target.",
                confidence=0.86 if len(refs) == 2 else 0.35,
                provenance=ProvenanceSource.HEURISTIC,
            )
        ],
        assumptions=list(problem.assumptions),
        confidence=0.84 if len(refs) == 2 else 0.3,
        provenance=ProvenanceSource.HEURISTIC,
        notes=["compiled_from_multiplicative_relation"],
    )


def _compile_partition_plan(problem: FormalizedProblem) -> ExecutablePlan:
    quantities = list(problem.quantities)
    target_ref = _target_ref(problem)
    refs = [quantity.quantity_id for quantity in quantities[:2]]
    expression = f"{refs[0]} / {refs[1]}" if len(refs) == 2 else "0"
    return ExecutablePlan(
        plan_id="plan_partition_grouping",
        target_ref=target_ref,
        steps=[
            ExecutableStep(
                step_id="step_1_divide",
                operation=TraceOperation.DIVIDE,
                expression=expression,
                input_refs=refs,
                output_ref=target_ref,
                explanation="Divide the total by the group count or group size.",
                confidence=0.84 if len(refs) == 2 else 0.3,
                provenance=ProvenanceSource.HEURISTIC,
            )
        ],
        assumptions=list(problem.assumptions),
        confidence=0.8 if len(refs) == 2 else 0.25,
        provenance=ProvenanceSource.HEURISTIC,
        notes=["compiled_from_partition_relation"],
    )


def _compile_unknown_plan(problem: FormalizedProblem, relation: RelationCandidate | None) -> ExecutablePlan:
    target_ref = _target_ref(problem)
    notes = ["compiled_from_unknown_relation"]

    if len(problem.quantities) == 1:
        quantity = problem.quantities[0]
        return ExecutablePlan(
            plan_id="plan_single_quantity",
            target_ref=target_ref,
            steps=[
                ExecutableStep(
                    step_id="step_1_single_quantity",
                    operation=TraceOperation.DERIVE,
                    expression=quantity.quantity_id,
                    input_refs=[quantity.quantity_id],
                    output_ref=target_ref,
                    explanation="Use the only extracted quantity as the target value.",
                    confidence=0.5,
                    provenance=ProvenanceSource.HEURISTIC,
                )
            ],
            assumptions=list(problem.assumptions),
            confidence=0.45,
            provenance=ProvenanceSource.HEURISTIC,
            notes=notes + ["used_single_quantity_fallback"],
        )

    if relation and relation.expression and not _is_placeholder_expression(relation.expression):
        rhs = relation.expression.split("=", 1)[-1].strip()
        return ExecutablePlan(
            plan_id="plan_unknown_relation_expression",
            target_ref=target_ref,
            steps=[
                ExecutableStep(
                    step_id="step_1_unknown_expression",
                    operation=TraceOperation.DERIVE,
                    expression=rhs,
                    input_refs=list(relation.source_quantity_ids),
                    output_ref=target_ref,
                    explanation="Fallback direct expression compiled from the relation candidate.",
                    confidence=0.35,
                    provenance=ProvenanceSource.HEURISTIC,
                )
            ],
            assumptions=list(problem.assumptions),
            confidence=0.3,
            provenance=ProvenanceSource.HEURISTIC,
            notes=notes + ["used_relation_expression"],
        )

    return ExecutablePlan(
        plan_id="plan_unresolved",
        target_ref=target_ref,
        steps=[],
        assumptions=list(problem.assumptions),
        confidence=0.0,
        provenance=ProvenanceSource.UNKNOWN,
        notes=notes + ["no_executable_strategy"],
    )


def compile_executable_plan(problem: FormalizedProblem) -> ExecutablePlan:
    """Compile a deterministic executable plan from a formalized problem."""
    graph_plan = _compile_problem_graph_plan(problem)
    if graph_plan is not None:
        return graph_plan

    relation = _resolved_relation(problem)
    relation_type = relation.relation_type if relation is not None else RelationType.UNKNOWN

    if relation_type == RelationType.RATE_UNIT_RELATION:
        return _compile_rate_plan(problem, relation)
    if relation_type == RelationType.ADDITIVE_COMPOSITION:
        return _compile_additive_plan(problem)
    if relation_type == RelationType.SUBTRACTIVE_COMPARISON:
        return _compile_subtractive_plan(problem)
    if relation_type == RelationType.MULTIPLICATIVE_SCALING:
        return _compile_multiplicative_plan(problem)
    if relation_type == RelationType.PARTITION_GROUPING:
        return _compile_partition_plan(problem)
    return _compile_unknown_plan(problem, relation)
