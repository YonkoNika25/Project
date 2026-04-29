"""Global alignment and graph-comparison helpers for evidence building."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.models import (
    CanonicalReference,
    FormalizedProblem,
    ProblemGraphEdgeType,
    ProblemGraphNodeType,
    StudentStepAttempt,
    StudentWorkState,
    TraceOperation,
)


@dataclass
class StepGraphPayload:
    step_id: str
    output_ref: str | None
    operation: TraceOperation
    input_refs: list[str]
    dependency_step_ids: list[str]
    output_value: float | None


@dataclass
class StepAlignment:
    student_step_id: str
    reference_step_id: str | None
    matched_output_ref: str | None
    score: float
    reasons: list[str]
    relationship: str
    dependency_overlap: list[str]
    missing_dependencies: list[str]
    extra_dependencies: list[str]


@dataclass
class GraphEditSummary:
    node_substitutions: int
    node_deletions: int
    node_insertions: int
    edge_substitutions: int
    edge_deletions: int
    edge_insertions: int
    total_cost: int


def values_match(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) < 1e-9


def reference_steps(reference: CanonicalReference) -> list[StepGraphPayload]:
    produced_refs = {step.output_ref for step in reference.chosen_plan.steps}
    payload: list[StepGraphPayload] = []
    for step, result in zip(reference.chosen_plan.steps, reference.execution_trace.step_results):
        dependency_step_ids = [
            prior_step.step_id
            for prior_step in reference.chosen_plan.steps
            if prior_step.output_ref in step.input_refs
        ]
        payload.append(
            StepGraphPayload(
                step_id=step.step_id,
                output_ref=step.output_ref,
                operation=step.operation,
                input_refs=list(step.input_refs),
                dependency_step_ids=dependency_step_ids,
                output_value=result.output_value if result.success else None,
            )
        )
    return payload


def student_steps(student: StudentWorkState) -> list[StepGraphPayload]:
    output_node_to_step_id: dict[str, str] = {}
    step_to_output_node: dict[str, str] = {}
    dependency_edges_to_step: dict[str, list[str]] = {}
    step_order = {step.step_id: index for index, step in enumerate(student.steps)}
    semantic_fact_by_id = {fact.fact_id: fact for fact in student.semantic_facts}

    def _semantic_fact_supporting_steps(fact_id: str, target_step_id: str) -> list[str]:
        fact = semantic_fact_by_id.get(fact_id)
        if fact is None:
            return []
        target_index = step_order.get(target_step_id, len(student.steps))
        supporting: list[str] = []
        for candidate in student.steps:
            candidate_index = step_order.get(candidate.step_id, len(student.steps))
            if candidate_index >= target_index:
                continue
            if fact.grounding and fact.grounding.strip() and fact.grounding.strip() in candidate.raw_text:
                supporting.append(candidate.step_id)
                continue
            if fact.value is not None and values_match(candidate.extracted_value, fact.value):
                supporting.append(candidate.step_id)
        return supporting

    graph = student.student_graph
    if graph is not None:
        for edge in graph.edges:
            if edge.edge_type == ProblemGraphEdgeType.OUTPUT_FROM_OPERATION:
                source_node = next((node for node in graph.nodes if node.node_id == edge.source_node_id), None)
                target_node = next((node for node in graph.nodes if node.node_id == edge.target_node_id), None)
                if source_node is not None and target_node is not None and source_node.step_id is not None:
                    output_node_to_step_id[target_node.node_id] = source_node.step_id
                    step_to_output_node[source_node.step_id] = target_node.node_id

        for edge in graph.edges:
            if edge.edge_type != ProblemGraphEdgeType.INPUT_TO_OPERATION:
                continue
            target_node = next((node for node in graph.nodes if node.node_id == edge.target_node_id), None)
            if target_node is None or target_node.node_type != ProblemGraphNodeType.OPERATION or target_node.step_id is None:
                continue
            source_step_id = output_node_to_step_id.get(edge.source_node_id)
            if source_step_id is not None:
                dependency_edges_to_step.setdefault(target_node.step_id, []).append(source_step_id)
                continue
            if edge.source_node_id in semantic_fact_by_id:
                dependency_edges_to_step.setdefault(target_node.step_id, []).extend(
                    _semantic_fact_supporting_steps(edge.source_node_id, target_node.step_id)
                )

    payload: list[StepGraphPayload] = []
    for step in student.steps:
        dependency_step_ids = dependency_edges_to_step.get(step.step_id, [])
        deduped_dependencies: list[str] = []
        seen_dependencies: set[str] = set()
        for dependency_step_id in dependency_step_ids:
            if dependency_step_id in seen_dependencies:
                continue
            seen_dependencies.add(dependency_step_id)
            deduped_dependencies.append(dependency_step_id)
        payload.append(
            StepGraphPayload(
                step_id=step.step_id,
                output_ref=step_to_output_node.get(step.step_id),
                operation=step.operation or TraceOperation.UNKNOWN,
                input_refs=list(step.referenced_ids),
                dependency_step_ids=deduped_dependencies,
                output_value=step.extracted_value,
            )
        )
    return payload


def infer_student_target_ref(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    student: StudentWorkState,
) -> str | None:
    if student.selected_target_ref is not None:
        return student.selected_target_ref

    graph = student.student_graph
    if graph is not None and graph.target_node_id is not None:
        incoming_target_edges = [
            edge
            for edge in graph.edges
            if edge.edge_type == ProblemGraphEdgeType.TARGETS_VALUE and edge.target_node_id == graph.target_node_id
        ]
        visible_problem_refs = {quantity.quantity_id for quantity in problem.quantities}
        reference_output_refs = {step.output_ref for step in reference.chosen_plan.steps}
        for edge in incoming_target_edges:
            source_ref = edge.source_node_id
            if source_ref == reference.chosen_plan.target_ref:
                return source_ref
            if source_ref in reference_output_refs:
                return source_ref
            if source_ref in visible_problem_refs:
                return source_ref

    return None


def _local_match_score(
    student_step: StepGraphPayload,
    reference_step: StepGraphPayload,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    overlap = sorted(set(student_step.input_refs).intersection(reference_step.input_refs))

    if values_match(student_step.output_value, reference_step.output_value):
        score += 6.0
        reasons.append("output_value_match")

    if (
        student_step.operation != TraceOperation.UNKNOWN
        and student_step.operation == reference_step.operation
        and (student_step.output_value is not None or overlap)
    ):
        score += 3.0
        reasons.append("operation_match")

    if overlap:
        score += min(2.0, float(len(overlap)))
        reasons.append(f"input_overlap:{','.join(overlap)}")

    if student_step.output_value is not None and reference_step.output_value is not None:
        score -= min(abs(student_step.output_value - reference_step.output_value) / 50.0, 1.5)

    return score, reasons


def global_align_student_steps(
    student: StudentWorkState,
    reference: CanonicalReference,
) -> list[StepAlignment]:
    student_payload = student_steps(student)
    reference_payload = reference_steps(reference)
    score_matrix = [
        [_local_match_score(student_step, reference_step)[0] for reference_step in reference_payload]
        for student_step in student_payload
    ]

    @lru_cache(maxsize=None)
    def _solve(student_index: int, used_mask: int) -> tuple[float, tuple[tuple[int, int], ...]]:
        if student_index >= len(student_payload):
            return 0.0, ()

        best_score, best_pairs = _solve(student_index + 1, used_mask)
        best_score -= 1.25  # cost for leaving this student step unmatched

        for ref_index in range(len(reference_payload)):
            if used_mask & (1 << ref_index):
                continue
            local_score = score_matrix[student_index][ref_index]
            if local_score <= 0.0:
                continue
            downstream_score, downstream_pairs = _solve(student_index + 1, used_mask | (1 << ref_index))
            candidate_score = local_score + downstream_score
            if candidate_score > best_score:
                best_score = candidate_score
                best_pairs = ((student_index, ref_index),) + downstream_pairs

        return best_score, best_pairs

    _, pairs = _solve(0, 0)
    student_to_reference = {student_index: ref_index for student_index, ref_index in pairs}

    reference_by_step_id = {step.step_id: step for step in reference_payload}
    reverse_pair = {
        student_payload[student_index].step_id: reference_payload[ref_index].step_id
        for student_index, ref_index in pairs
    }
    inverse_reverse_pair = {ref_step_id: student_step_id for student_step_id, ref_step_id in reverse_pair.items()}

    alignments: list[StepAlignment] = []
    for student_index, student_step in enumerate(student_payload):
        ref_index = student_to_reference.get(student_index)
        if ref_index is None:
            alignments.append(
                StepAlignment(
                    student_step_id=student_step.step_id,
                    reference_step_id=None,
                    matched_output_ref=None,
                    score=0.0,
                    reasons=["unmatched_in_global_alignment"],
                    relationship="unsupported",
                    dependency_overlap=[],
                    missing_dependencies=[],
                    extra_dependencies=[],
                )
            )
            continue

        reference_step = reference_payload[ref_index]
        score, reasons = _local_match_score(student_step, reference_step)
        mapped_student_deps = {
            reverse_pair.get(dep_step_id, f"student:{dep_step_id}")
            for dep_step_id in student_step.dependency_step_ids
        }
        reference_deps = set(reference_step.dependency_step_ids)
        dependency_overlap = sorted(mapped_student_deps.intersection(reference_deps))
        missing_dependencies = sorted(reference_deps - mapped_student_deps)
        extra_dependencies = sorted(mapped_student_deps - reference_deps)

        relationship = "aligned"
        if not values_match(student_step.output_value, reference_step.output_value):
            relationship = "value_mismatch"
        elif (
            student_step.operation != TraceOperation.UNKNOWN
            and student_step.operation != reference_step.operation
        ):
            relationship = "value_match_operation_mismatch"
        elif missing_dependencies or extra_dependencies:
            relationship = "dependency_mismatch"

        if relationship == "aligned" and not dependency_overlap and reference_deps:
            relationship = "dependency_mismatch"

        if relationship == "aligned" and student_step.output_value is None:
            relationship = "ambiguous"

        alignments.append(
            StepAlignment(
                student_step_id=student_step.step_id,
                reference_step_id=reference_step.step_id,
                matched_output_ref=reference_step.output_ref,
                score=score,
                reasons=reasons,
                relationship=relationship,
                dependency_overlap=dependency_overlap,
                missing_dependencies=missing_dependencies,
                extra_dependencies=extra_dependencies,
            )
        )

    return alignments


def detect_reordered_but_consistent(
    student: StudentWorkState,
    reference: CanonicalReference,
    alignments: list[StepAlignment],
) -> bool:
    if student.normalized_final_answer is None or not values_match(student.normalized_final_answer, reference.final_answer):
        return False

    aligned = [
        item
        for item in alignments
        if item.reference_step_id is not None and item.relationship in {"aligned", "dependency_mismatch"}
    ]
    if len(aligned) < 2:
        return False

    reference_index = {step.step_id: index for index, step in enumerate(reference.chosen_plan.steps)}
    aligned_order = [reference_index[item.reference_step_id] for item in aligned if item.reference_step_id in reference_index]
    if len(aligned_order) < 2:
        return False
    return aligned_order != sorted(aligned_order)


def student_graph_has_target_path(student: StudentWorkState) -> bool:
    graph = student.student_graph
    if graph is None or graph.target_node_id is None:
        return False
    return any(
        edge.target_node_id == graph.target_node_id and edge.edge_type == ProblemGraphEdgeType.TARGETS_VALUE
        for edge in graph.edges
    )


def graph_edit_summary(
    reference: CanonicalReference,
    alignments: list[StepAlignment],
) -> GraphEditSummary:
    reference_payload = reference_steps(reference)
    alignment_by_ref = {item.reference_step_id: item for item in alignments if item.reference_step_id is not None}
    matched_reference_step_ids = set(alignment_by_ref.keys())
    matched_student_step_ids = {item.student_step_id for item in alignments if item.reference_step_id is not None}

    node_substitutions = sum(
        1 for item in alignments if item.reference_step_id is not None and item.relationship in {"value_mismatch", "value_match_operation_mismatch", "dependency_mismatch"}
    )
    node_insertions = sum(1 for item in alignments if item.reference_step_id is None)
    node_deletions = sum(1 for step in reference_payload if step.step_id not in matched_reference_step_ids)

    edge_substitutions = 0
    edge_deletions = 0
    edge_insertions = 0
    for item in alignments:
        if item.reference_step_id is None:
            continue
        edge_substitutions += len(item.missing_dependencies) + len(item.extra_dependencies)
        edge_deletions += len(item.missing_dependencies)
        edge_insertions += len(item.extra_dependencies)

    total_cost = node_substitutions + node_insertions + node_deletions + edge_substitutions
    return GraphEditSummary(
        node_substitutions=node_substitutions,
        node_deletions=node_deletions,
        node_insertions=node_insertions,
        edge_substitutions=edge_substitutions,
        edge_deletions=edge_deletions,
        edge_insertions=edge_insertions,
        total_cost=total_cost,
    )
