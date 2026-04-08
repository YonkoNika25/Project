"""Build structured diagnosis evidence from problem, reference, and student artifacts."""
from __future__ import annotations

from src.evidence.alignment import (
    global_align_student_steps,
    detect_reordered_but_consistent,
    graph_edit_summary,
    infer_student_target_ref,
    student_graph_has_target_path,
    values_match,
)
from src.models import (
    CanonicalReference,
    DiagnosisEvidence,
    EvidenceItem,
    FormalizedProblem,
    StudentWorkMode,
    StudentWorkState,
    TraceOperation,
)


def _reference_output_to_step_id(reference: CanonicalReference) -> dict[str, str]:
    return {step.output_ref: step.step_id for step in reference.chosen_plan.steps}


def _student_target_linked_output_step_id(student: StudentWorkState) -> str | None:
    graph = student.student_graph
    if graph is None or graph.target_node_id is None:
        return None
    linked_output_node_id = next(
        (
            edge.source_node_id
            for edge in graph.edges
            if edge.edge_type.value == "targets_value"
            and edge.target_node_id == graph.target_node_id
            and edge.source_node_id.startswith("student_output_")
        ),
        None,
    )
    if linked_output_node_id is None:
        return None
    output_edge = next(
        (
            edge
            for edge in graph.edges
            if edge.edge_type.value == "output_from_operation"
            and edge.target_node_id == linked_output_node_id
        ),
        None,
    )
    if output_edge is None:
        return None
    operation_node = next((node for node in graph.nodes if node.node_id == output_edge.source_node_id), None)
    return operation_node.step_id if operation_node is not None else None


def _unique_visible_problem_quantity(problem: FormalizedProblem, value: float | None):
    if value is None:
        return None
    matches = [quantity for quantity in problem.quantities if values_match(quantity.value, value)]
    return matches[0] if len(matches) == 1 else None


def _build_unparseable_evidence() -> DiagnosisEvidence:
    return DiagnosisEvidence(
        evidence_items=[
            EvidenceItem(
                evidence_type="unparseable_answer",
                description="The student answer could not be normalized into a numeric target.",
                confidence=0.96,
            )
        ],
        alignment_map=[],
        first_divergence_step_id=None,
        likely_error_mechanisms=["unparseable_answer"],
        confidence=0.94,
        notes=["student_work_unparseable"],
    )


def _alignment_payload(alignments) -> list[dict]:
    return [
        {
            "student_step_id": item.student_step_id,
            "reference_step_id": item.reference_step_id,
            "matched_output_ref": item.matched_output_ref,
            "score": item.score,
            "relationship": item.relationship,
            "reasons": list(item.reasons),
            "dependency_overlap": list(item.dependency_overlap),
            "missing_dependencies": list(item.missing_dependencies),
            "extra_dependencies": list(item.extra_dependencies),
        }
        for item in alignments
    ]


def build_diagnosis_evidence(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    student: StudentWorkState,
) -> DiagnosisEvidence:
    """Build structured evidence that can be consumed by the diagnosis layer."""
    if student.mode == StudentWorkMode.UNPARSEABLE or student.normalized_final_answer is None:
        return _build_unparseable_evidence()

    evidence_items: list[EvidenceItem] = []
    mechanisms: list[str] = []
    notes: list[str] = [f"student_mode={student.mode.value}"]
    first_divergence_step_id: str | None = None
    target_ref = reference.chosen_plan.target_ref
    output_ref_to_step_id = _reference_output_to_step_id(reference)
    inferred_target_ref = infer_student_target_ref(problem, reference, student)
    alignments = global_align_student_steps(student, reference)
    alignment_map = _alignment_payload(alignments)
    alignment_by_student_step_id = {item.student_step_id: item for item in alignments}
    reordered_consistent = detect_reordered_but_consistent(student, reference, alignments)
    student_steps_by_id = {step.step_id: step for step in student.steps}
    edit_summary = graph_edit_summary(reference, alignments)

    if student_graph_has_target_path(student):
        evidence_items.append(
            EvidenceItem(
                evidence_type="graph_target_path_present",
                description="The student graph contains a path into the student target node.",
                confidence=0.72,
            )
        )
    elif student.student_graph is not None:
        evidence_items.append(
            EvidenceItem(
                evidence_type="graph_target_path_missing",
                description="The student graph does not show a supported path into the student target node.",
                confidence=0.78,
            )
        )

    if values_match(student.normalized_final_answer, reference.final_answer):
        evidence_items.append(
            EvidenceItem(
                evidence_type="correct_final_answer",
                description="The student's normalized final answer matches the canonical reference answer.",
                confidence=0.98,
                reference_step_id=output_ref_to_step_id.get(target_ref),
                metadata={"student_final_answer": student.normalized_final_answer},
            )
        )
    else:
        evidence_items.append(
            EvidenceItem(
                evidence_type="final_answer_mismatch",
                description="The student's normalized final answer does not match the canonical reference answer.",
                confidence=0.9,
                reference_step_id=output_ref_to_step_id.get(target_ref),
                metadata={
                    "student_final_answer": student.normalized_final_answer,
                    "reference_final_answer": reference.final_answer,
                },
            )
        )
        mechanisms.append("final_answer_mismatch")

    if inferred_target_ref is not None:
        if inferred_target_ref == target_ref:
            evidence_items.append(
                EvidenceItem(
                    evidence_type="target_ref_match",
                    description="The student's answer appears to target the same final variable as the canonical plan.",
                    confidence=0.88,
                    reference_step_id=output_ref_to_step_id.get(target_ref),
                    metadata={"selected_target_ref": inferred_target_ref},
                )
            )
        elif inferred_target_ref in output_ref_to_step_id:
            matched_step_id = output_ref_to_step_id[inferred_target_ref]
            evidence_items.append(
                EvidenceItem(
                    evidence_type="selected_intermediate_reference",
                    description="The student's answer matches an intermediate value produced by the canonical plan.",
                    confidence=0.94,
                    reference_step_id=matched_step_id,
                    metadata={"selected_target_ref": inferred_target_ref},
                )
            )
            if "selected_intermediate_target" not in mechanisms:
                mechanisms.append("selected_intermediate_target")
            if first_divergence_step_id is None:
                first_divergence_step_id = matched_step_id
        else:
            quantity = next((candidate for candidate in problem.quantities if candidate.quantity_id == inferred_target_ref), None)
            if quantity is not None:
                evidence_items.append(
                    EvidenceItem(
                        evidence_type="selected_visible_problem_quantity",
                        description="The student's answer matches a visible quantity from the problem text instead of the final target.",
                        confidence=0.9,
                        quantity_ids=[quantity.quantity_id],
                        metadata={
                            "selected_target_ref": inferred_target_ref,
                            "quantity_value": quantity.value,
                        },
                    )
                )
                if "selected_visible_quantity_as_answer" not in mechanisms:
                    mechanisms.append("selected_visible_quantity_as_answer")
    else:
        linked_output_step_id = _student_target_linked_output_step_id(student)
        if linked_output_step_id is not None:
            linked_alignment = alignment_by_student_step_id.get(linked_output_step_id)
            if linked_alignment is not None and linked_alignment.reference_step_id is not None:
                matched_reference_output = linked_alignment.matched_output_ref
                if matched_reference_output is not None and matched_reference_output != target_ref:
                    matched_step_id = linked_alignment.reference_step_id
                    evidence_items.append(
                        EvidenceItem(
                            evidence_type="selected_intermediate_reference",
                            description="The student graph targets a student-produced value aligned to an intermediate canonical reference output.",
                            confidence=0.92,
                            reference_step_id=matched_step_id,
                            student_step_id=linked_output_step_id,
                            metadata={"matched_output_ref": matched_reference_output},
                        )
                    )
                    if "selected_intermediate_target" not in mechanisms:
                        mechanisms.append("selected_intermediate_target")
                    if first_divergence_step_id is None:
                        first_divergence_step_id = matched_step_id

        if linked_output_step_id is None:
            matched_quantity = _unique_visible_problem_quantity(problem, student.normalized_final_answer)
            if matched_quantity is not None:
                evidence_items.append(
                    EvidenceItem(
                        evidence_type="selected_visible_problem_quantity",
                        description="The student's final answer exactly matches one visible quantity from the problem text without evidence of solving for the requested target.",
                        confidence=0.82,
                        quantity_ids=[matched_quantity.quantity_id],
                        metadata={
                            "selected_target_ref": matched_quantity.quantity_id,
                            "quantity_value": matched_quantity.value,
                        },
                    )
                )
                if "selected_visible_quantity_as_answer" not in mechanisms:
                    mechanisms.append("selected_visible_quantity_as_answer")

    if reordered_consistent:
        evidence_items.append(
            EvidenceItem(
                evidence_type="reordered_but_consistent_steps",
                description="The student appears to compute canonical intermediate quantities in a different order while preserving a consistent dependency chain.",
                confidence=0.87,
                metadata={"alignment_map_size": len(alignment_map)},
            )
        )

    evidence_items.append(
        EvidenceItem(
            evidence_type="graph_edit_distance",
            description="A graph-level edit summary was computed between the aligned student process and the canonical reference process.",
            confidence=0.76,
            metadata={
                "node_substitutions": edit_summary.node_substitutions,
                "node_deletions": edit_summary.node_deletions,
                "node_insertions": edit_summary.node_insertions,
                "edge_substitutions": edit_summary.edge_substitutions,
                "edge_deletions": edit_summary.edge_deletions,
                "edge_insertions": edit_summary.edge_insertions,
                "total_cost": edit_summary.total_cost,
            },
        )
    )

    reference_step_ids = {step.step_id for step in reference.chosen_plan.steps}
    matched_reference_step_ids = {
        item["reference_step_id"] for item in alignment_map if item["reference_step_id"] is not None
    }

    for item in alignment_map:
        if item["reference_step_id"] is None:
            student_step = student_steps_by_id.get(item["student_step_id"])
            if (
                student_step is not None
                and student_step.operation == TraceOperation.DERIVE
                and values_match(student_step.extracted_value, student.normalized_final_answer)
            ):
                evidence_items.append(
                    EvidenceItem(
                        evidence_type="restated_final_answer",
                        description="The student restates the final answer after already producing a structured solution step.",
                        confidence=0.72,
                        student_step_id=item["student_step_id"],
                        metadata={"reasons": item["reasons"], "score": item["score"]},
                    )
                )
                continue
            evidence_items.append(
                EvidenceItem(
                    evidence_type="unsupported_student_step",
                    description="A student step could not be confidently aligned to any canonical reference step.",
                    confidence=0.7,
                    student_step_id=item["student_step_id"],
                    metadata={"reasons": item["reasons"], "score": item["score"]},
                )
            )
            if "unsupported_step" not in mechanisms:
                mechanisms.append("unsupported_step")
            continue

        if item["relationship"] == "aligned":
            evidence_items.append(
                EvidenceItem(
                    evidence_type="step_value_match",
                    description="A student step reproduces a value present in the canonical execution trace.",
                    confidence=0.78,
                    reference_step_id=item["reference_step_id"],
                    student_step_id=item["student_step_id"],
                    metadata={"matched_output_ref": item["matched_output_ref"], "reasons": item["reasons"]},
                )
            )
            continue

        if item["relationship"] == "dependency_mismatch":
            evidence_items.append(
                EvidenceItem(
                    evidence_type="dependency_mismatch",
                    description="A student step aligns to a canonical step by value/operation but diverges in its dependency subgraph.",
                    confidence=0.86,
                    reference_step_id=item["reference_step_id"],
                    student_step_id=item["student_step_id"],
                    metadata={
                        "matched_output_ref": item["matched_output_ref"],
                        "dependency_overlap": item["dependency_overlap"],
                        "missing_dependencies": item["missing_dependencies"],
                        "extra_dependencies": item["extra_dependencies"],
                    },
                )
            )
            evidence_items.append(
                EvidenceItem(
                    evidence_type="edge_level_divergence",
                    description="Aligned student and canonical steps differ in one or more dependency edges.",
                    confidence=0.84,
                    reference_step_id=item["reference_step_id"],
                    student_step_id=item["student_step_id"],
                    metadata={
                        "missing_dependencies": item["missing_dependencies"],
                        "extra_dependencies": item["extra_dependencies"],
                    },
                )
            )
            if "dependency_mismatch" not in mechanisms:
                mechanisms.append("dependency_mismatch")
            if first_divergence_step_id is None:
                first_divergence_step_id = item["reference_step_id"]
            continue

        if item["relationship"] == "value_match_operation_mismatch":
            student_step = student_steps_by_id.get(item["student_step_id"])
            if (
                student_step is not None
                and student_step.operation == TraceOperation.DERIVE
                and item["matched_output_ref"] == target_ref
                and values_match(student.normalized_final_answer, reference.final_answer)
            ):
                evidence_items.append(
                    EvidenceItem(
                        evidence_type="restated_final_answer",
                        description="The student restates the final answer after already producing the correct target value.",
                        confidence=0.72,
                        reference_step_id=item["reference_step_id"],
                        student_step_id=item["student_step_id"],
                        metadata={"reasons": item["reasons"]},
                    )
                )
                continue
            evidence_items.append(
                EvidenceItem(
                    evidence_type="operation_mismatch",
                    description="A student step lands on a canonical value but appears to use a different operation label than the aligned canonical step.",
                    confidence=0.82,
                    reference_step_id=item["reference_step_id"],
                    student_step_id=item["student_step_id"],
                    metadata={"matched_output_ref": item["matched_output_ref"], "reasons": item["reasons"]},
                )
            )
            if "operation_mismatch" not in mechanisms:
                mechanisms.append("operation_mismatch")
            if first_divergence_step_id is None:
                first_divergence_step_id = item["reference_step_id"]
            continue

        if item["relationship"] == "value_mismatch":
            evidence_items.append(
                EvidenceItem(
                    evidence_type="step_value_mismatch",
                    description="A student step appears aligned to a canonical step but produces a different value.",
                    confidence=0.84,
                    reference_step_id=item["reference_step_id"],
                    student_step_id=item["student_step_id"],
                    metadata={"matched_output_ref": item["matched_output_ref"], "reasons": item["reasons"]},
                )
            )
            if "arithmetic_mismatch" not in mechanisms:
                mechanisms.append("arithmetic_mismatch")
            if first_divergence_step_id is None:
                first_divergence_step_id = item["reference_step_id"]

    if values_match(student.normalized_final_answer, reference.final_answer):
        if reference_step_ids - matched_reference_step_ids and not reordered_consistent:
            notes.append("correct_final_answer_with_partial_process_coverage")
    else:
        missing_reference_step_ids = sorted(reference_step_ids - matched_reference_step_ids)
        if missing_reference_step_ids:
            evidence_items.append(
                EvidenceItem(
                    evidence_type="missing_reference_steps",
                    description="Some canonical reference steps were not evidenced in the student process alignment.",
                    confidence=0.74,
                    metadata={"missing_reference_step_ids": missing_reference_step_ids},
                )
            )
            if "missing_step" not in mechanisms:
                mechanisms.append("missing_step")
            if first_divergence_step_id is None:
                first_divergence_step_id = missing_reference_step_ids[0]

    if edit_summary.total_cost > 0 and not reordered_consistent and "graph_edit_distance_nonzero" not in mechanisms:
        mechanisms.append("graph_edit_distance_nonzero")

    if (
        not values_match(student.normalized_final_answer, reference.final_answer)
        and inferred_target_ref == target_ref
        and "arithmetic_mismatch" not in mechanisms
        and "selected_intermediate_target" not in mechanisms
    ):
        evidence_items.append(
            EvidenceItem(
                evidence_type="target_correct_but_value_wrong",
                description="The student appears to target the right final variable but lands on the wrong numeric value.",
                confidence=0.82,
                reference_step_id=output_ref_to_step_id.get(target_ref),
                metadata={"student_final_answer": student.normalized_final_answer},
            )
        )
        mechanisms.append("arithmetic_mismatch")
        if first_divergence_step_id is None:
            first_divergence_step_id = output_ref_to_step_id.get(target_ref)

    if not evidence_items:
        evidence_items.append(
            EvidenceItem(
                evidence_type="insufficient_alignment_signal",
                description="The available structured artifacts did not expose a strong divergence pattern.",
                confidence=0.3,
            )
        )
        notes.append("insufficient_alignment_signal")

    confidence = min(
        0.25 + sum(item.confidence for item in evidence_items) / max(len(evidence_items), 1) * 0.75,
        0.97,
    )

    return DiagnosisEvidence(
        evidence_items=evidence_items,
        alignment_map=alignment_map,
        first_divergence_step_id=first_divergence_step_id,
        likely_error_mechanisms=mechanisms,
        confidence=confidence,
        notes=notes,
    )
