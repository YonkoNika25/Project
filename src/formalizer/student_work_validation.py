"""Validation and feedback helpers for semantic-sketch student-work formalization."""
from __future__ import annotations

from src.models import (
    CanonicalReference,
    FormalizedProblem,
    GraphValidationIssue,
    GraphValidationResult,
    StudentWorkMode,
    StudentWorkState,
    TraceOperation,
)


def _student_feedback_payload(validation_result: GraphValidationResult) -> list[dict]:
    payload: list[dict] = []
    for issue in validation_result.issues:
        payload.append(
            {
                "code": issue.code,
                "message": issue.message,
                "step_id": issue.step_id,
                "node_id": issue.node_id,
                "details": issue.details,
            }
        )
    return payload


def _student_sanity_validation_result(
    student_state: StudentWorkState,
    problem: FormalizedProblem | None,
    reference: CanonicalReference | None,
) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    allowed_problem_refs: set[str] = set()

    if problem is not None:
        allowed_problem_refs.update(quantity.quantity_id for quantity in problem.quantities)
        if problem.target is not None:
            allowed_problem_refs.add(problem.target.target_variable)

    allowed_step_refs = set(allowed_problem_refs)
    allowed_step_refs.update(fact.fact_id for fact in student_state.semantic_facts)

    if student_state.selected_target_ref is not None and student_state.selected_target_ref not in allowed_problem_refs:
        issues.append(
            GraphValidationIssue(
                code="student_invalid_selected_target_ref",
                message="selected_target_ref must come from the known problem refs",
                details={"selected_target_ref": student_state.selected_target_ref},
            )
        )

    for step in student_state.steps:
        unknown_refs = [ref_id for ref_id in step.referenced_ids if ref_id not in allowed_step_refs]
        if unknown_refs:
            issues.append(
                GraphValidationIssue(
                    code="student_unknown_referenced_ids",
                    message="Student step referenced_ids must use only known problem refs or semantic fact ids",
                    step_id=step.step_id,
                    details={"unknown_refs": unknown_refs},
                )
            )
        if step.operation is None:
            issues.append(
                GraphValidationIssue(
                    code="student_missing_operation",
                    message="Student step operation must not be null after local build",
                    step_id=step.step_id,
                )
            )

    if student_state.mode == StudentWorkMode.FINAL_ANSWER_ONLY and student_state.normalized_final_answer is None:
        issues.append(
            GraphValidationIssue(
                code="student_missing_final_answer",
                message="final_answer_only mode requires normalized_final_answer",
            )
        )
    if student_state.mode == StudentWorkMode.FINAL_ANSWER_ONLY and student_state.steps:
        issues.append(
            GraphValidationIssue(
                code="student_final_answer_only_with_steps",
                message="final_answer_only mode must not include structured steps",
            )
        )
    if student_state.mode == StudentWorkMode.UNPARSEABLE and (
        student_state.steps or student_state.normalized_final_answer is not None
    ):
        issues.append(
            GraphValidationIssue(
                code="student_unparseable_with_structure",
                message="unparseable mode must not include parseable final answer or structured steps",
            )
        )

    if student_state.mode in {StudentWorkMode.PARTIAL_TRACE, StudentWorkMode.FULL_TRACE} and not student_state.steps:
        issues.append(
            GraphValidationIssue(
                code="student_trace_mode_missing_steps",
                message="partial/full trace mode requires at least one structured step",
            )
        )

    has_structured_step = any(
        step.extracted_value is not None or step.operation not in {None, TraceOperation.UNKNOWN}
        for step in student_state.steps
    )
    if student_state.student_graph is None and (student_state.normalized_final_answer is not None or has_structured_step):
        issues.append(
            GraphValidationIssue(
                code="student_missing_graph",
                message="Student work with parseable structure must include student_graph",
            )
        )

    if student_state.student_graph is not None and student_state.student_graph.target_node_id is None:
        issues.append(
            GraphValidationIssue(
                code="student_graph_missing_target",
                message="student_graph must define target_node_id when present",
            )
        )

    return GraphValidationResult(
        is_valid=not issues,
        issues=issues,
        target_node_id=student_state.student_graph.target_node_id if student_state.student_graph is not None else None,
        operation_node_count=(
            len(
                [
                    node
                    for node in student_state.student_graph.nodes
                    if node.node_type.value == "operation"
                ]
            )
            if student_state.student_graph is not None
            else 0
        ),
        notes=["student_sanity_validation"],
    )
