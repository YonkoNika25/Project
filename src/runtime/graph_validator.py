"""Structured validation for problem graphs before compilation/execution."""
from __future__ import annotations

import ast

from src.models import (
    FormalizedProblem,
    GraphValidationIssue,
    GraphValidationResult,
    ProblemGraphEdgeType,
    ProblemGraphNodeType,
    TraceOperation,
)


def _issue(
    code: str,
    message: str,
    *,
    node_id: str | None = None,
    edge_id: str | None = None,
    step_id: str | None = None,
    **details,
) -> GraphValidationIssue:
    return GraphValidationIssue(
        code=code,
        message=message,
        node_id=node_id,
        edge_id=edge_id,
        step_id=step_id,
        details=details,
    )


def _is_zero_input_constant_expression(expression: str | None) -> bool:
    if not expression or not expression.strip():
        return False
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        return False

    for node in ast.walk(parsed):
        if isinstance(node, ast.Name):
            return False
    return True


def validate_problem_graph(problem: FormalizedProblem) -> GraphValidationResult:
    """Validate that a problem graph can be compiled and executed safely."""
    graph = problem.problem_graph
    issues: list[GraphValidationIssue] = []
    notes: list[str] = []

    if graph is None:
        issues.append(_issue("missing_problem_graph", "FormalizedProblem does not contain a problem_graph"))
        return GraphValidationResult(is_valid=False, issues=issues, operation_node_count=0, notes=notes)

    nodes_by_id = {node.node_id: node for node in graph.nodes}
    operation_nodes = sorted(
        (node for node in graph.nodes if node.node_type == ProblemGraphNodeType.OPERATION),
        key=lambda node: node.step_index or 0,
    )
    if not operation_nodes:
        issues.append(_issue("missing_operation_nodes", "Problem graph does not contain any operation nodes"))

    if graph.target_node_id is None:
        issues.append(_issue("missing_target_node_id", "Problem graph is missing target_node_id"))
    elif graph.target_node_id not in nodes_by_id:
        issues.append(
            _issue(
                "unknown_target_node_id",
                "Problem graph target_node_id does not exist in graph nodes",
                node_id=graph.target_node_id,
            )
        )

    step_ids = [node.step_id for node in operation_nodes if node.step_id is not None]
    if len(step_ids) != len(set(step_ids)):
        issues.append(_issue("duplicate_step_id", "Problem graph contains duplicate operation step_id values"))

    step_indexes = [node.step_index for node in operation_nodes if node.step_index is not None]
    if len(step_indexes) != len(set(step_indexes)):
        issues.append(_issue("duplicate_step_index", "Problem graph contains duplicate operation step_index values"))

    available_refs = {quantity.quantity_id for quantity in problem.quantities}
    notes.append(f"initial_available_refs={len(available_refs)}")

    for node in operation_nodes:
        step_id = node.step_id or node.node_id
        input_edges = sorted(
            (
                edge
                for edge in graph.edges
                if edge.edge_type == ProblemGraphEdgeType.INPUT_TO_OPERATION and edge.target_node_id == node.node_id
            ),
            key=lambda edge: edge.position if edge.position is not None else 999,
        )
        if not input_edges:
            if not (
                node.operation == TraceOperation.DERIVE and _is_zero_input_constant_expression(node.expression)
            ):
                issues.append(
                    _issue(
                        "operation_missing_inputs",
                        "Operation node does not have any input edges",
                        node_id=node.node_id,
                        step_id=step_id,
                    )
                )

        output_edges = [
            edge
            for edge in graph.edges
            if edge.edge_type == ProblemGraphEdgeType.OUTPUT_FROM_OPERATION and edge.source_node_id == node.node_id
        ]
        if len(output_edges) == 0:
            issues.append(
                _issue(
                    "operation_missing_output",
                    "Operation node does not produce an output edge",
                    node_id=node.node_id,
                    step_id=step_id,
                )
            )
            continue
        if len(output_edges) > 1:
            issues.append(
                _issue(
                    "operation_multiple_outputs",
                    "Operation node produces multiple output edges",
                    node_id=node.node_id,
                    step_id=step_id,
                    output_edge_count=len(output_edges),
                )
            )
            continue

        for edge in input_edges:
            source_node = nodes_by_id[edge.source_node_id]
            if source_node.node_type == ProblemGraphNodeType.ENTITY:
                issues.append(
                    _issue(
                        "entity_used_as_numeric_input",
                        "Entity node cannot be used directly as a numeric operation input",
                        node_id=source_node.node_id,
                        edge_id=edge.edge_id,
                        step_id=step_id,
                    )
                )
                continue

            input_ref = source_node.quantity_id or source_node.target_variable or source_node.node_id
            if input_ref not in available_refs:
                issues.append(
                    _issue(
                        "input_not_available",
                        "Operation input is referenced before it becomes available",
                        node_id=source_node.node_id,
                        edge_id=edge.edge_id,
                        step_id=step_id,
                        input_ref=input_ref,
                    )
                )

        output_node = nodes_by_id[output_edges[0].target_node_id]
        output_ref = output_node.target_variable or output_node.node_id
        available_refs.add(output_ref)

    if graph.target_node_id is not None and graph.target_node_id not in available_refs:
        issues.append(
            _issue(
                "target_not_produced",
                "The target node is not produced by any executable path in the graph",
                node_id=graph.target_node_id,
            )
        )

    return GraphValidationResult(
        is_valid=len(issues) == 0,
        issues=issues,
        target_node_id=graph.target_node_id,
        operation_node_count=len(operation_nodes),
        notes=notes,
    )
