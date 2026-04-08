"""Hypothesis scoring over structured evidence for grounded diagnosis."""
from __future__ import annotations

from dataclasses import dataclass

from src.models import DiagnosisEvidence, DiagnosisLabel, ErrorLocalization


@dataclass
class DiagnosisHypothesis:
    label: DiagnosisLabel
    subtype: str | None
    localization: ErrorLocalization
    summary: str
    score: float
    supporting_evidence_types: list[str]
    rationale: list[str]


def _evidence_types(evidence: DiagnosisEvidence) -> list[str]:
    return [item.evidence_type for item in evidence.evidence_items]


def _item_by_type(evidence: DiagnosisEvidence, evidence_type: str):
    return next((item for item in evidence.evidence_items if item.evidence_type == evidence_type), None)


def _has_type(evidence: DiagnosisEvidence, evidence_type: str) -> bool:
    return any(item.evidence_type == evidence_type for item in evidence.evidence_items)


def _graph_edit_cost(evidence: DiagnosisEvidence) -> int:
    item = _item_by_type(evidence, "graph_edit_distance")
    if item is None:
        return 0
    return int(item.metadata.get("total_cost", 0))


def _alignment_relationship_counts(evidence: DiagnosisEvidence) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in evidence.alignment_map:
        relationship = str(item.get("relationship", "unknown"))
        counts[relationship] = counts.get(relationship, 0) + 1
    return counts


def _score_correct_answer(evidence: DiagnosisEvidence) -> DiagnosisHypothesis:
    score = 0.0
    rationale: list[str] = []
    evidence_types = _evidence_types(evidence)
    edit_cost = _graph_edit_cost(evidence)

    if "correct_final_answer" in evidence_types:
        score += 6.5
        rationale.append("correct_final_answer")
    if "target_ref_match" in evidence_types:
        score += 1.5
        rationale.append("target_ref_match")
    if "reordered_but_consistent_steps" in evidence_types:
        score += 2.0
        rationale.append("reordered_but_consistent_steps")
    if "graph_target_path_present" in evidence_types:
        score += 0.5
        rationale.append("graph_target_path_present")
    if "restated_final_answer" in evidence_types:
        score += 0.4
        rationale.append("restated_final_answer")
    if edit_cost > 0 and "correct_final_answer" in evidence_types:
        score += max(0.0, 1.0 - min(edit_cost / 10.0, 1.0))
        rationale.append(f"graph_edit_cost={edit_cost}")

    if "final_answer_mismatch" in evidence_types:
        score -= 6.0
    if "selected_intermediate_reference" in evidence_types or "selected_visible_problem_quantity" in evidence_types:
        score -= 8.0
    if "operation_mismatch" in evidence_types:
        score -= 5.0 if "correct_final_answer" in evidence_types else 3.0
    if "dependency_mismatch" in evidence_types:
        score -= 4.0 if "correct_final_answer" in evidence_types else 2.5
    if "unsupported_student_step" in evidence_types:
        score -= 2.5 if "correct_final_answer" in evidence_types else 1.5
    if "step_value_mismatch" in evidence_types:
        score -= 3.5 if "correct_final_answer" in evidence_types else 2.0
    if edit_cost > 2:
        score -= min(edit_cost / 3.0, 3.0)

    subtype = "equivalent_reordered_process" if "reordered_but_consistent_steps" in evidence_types else "matches_canonical_reference"
    summary = (
        "The student's final answer matches the canonical reference, and the process remains consistent even if the step order differs."
        if subtype == "equivalent_reordered_process"
        else "The student's final answer matches the canonical reference."
    )
    return DiagnosisHypothesis(
        label=DiagnosisLabel.CORRECT_ANSWER,
        subtype=subtype,
        localization=ErrorLocalization.NONE,
        summary=summary,
        score=score,
        supporting_evidence_types=["correct_final_answer"],
        rationale=rationale,
    )


def _score_unparseable_answer(evidence: DiagnosisEvidence) -> DiagnosisHypothesis:
    evidence_types = _evidence_types(evidence)
    score = 10.0 if "unparseable_answer" in evidence_types else 0.0
    rationale = ["unparseable_answer"] if score else []
    return DiagnosisHypothesis(
        label=DiagnosisLabel.UNPARSEABLE_ANSWER,
        subtype="answer_not_numeric",
        localization=ErrorLocalization.UNKNOWN,
        summary="The student answer could not be normalized into a usable numeric target.",
        score=score,
        supporting_evidence_types=["unparseable_answer"],
        rationale=rationale,
    )


def _score_target_misunderstanding(evidence: DiagnosisEvidence) -> DiagnosisHypothesis:
    evidence_types = _evidence_types(evidence)
    score = 0.0
    rationale: list[str] = []

    subtype = "target_selection_ambiguous"
    summary = "The student appears to target a quantity other than the requested final target."

    if "selected_intermediate_reference" in evidence_types:
        score += 8.0
        rationale.append("selected_intermediate_reference")
        subtype = "selected_intermediate_quantity"
        summary = "The student appears to have stopped at an intermediate quantity instead of the final target."

    if "selected_visible_problem_quantity" in evidence_types:
        score += 8.0
        rationale.append("selected_visible_problem_quantity")
        subtype = "selected_visible_problem_quantity"
        summary = "The student appears to have answered with a quantity mentioned in the problem rather than the requested target."

    if "final_answer_mismatch" in evidence_types:
        score += 1.0
        rationale.append("final_answer_mismatch")

    if "target_ref_match" in evidence_types:
        score -= 4.0

    return DiagnosisHypothesis(
        label=DiagnosisLabel.TARGET_MISUNDERSTANDING,
        subtype=subtype,
        localization=ErrorLocalization.TARGET_SELECTION,
        summary=summary,
        score=score,
        supporting_evidence_types=[item for item in evidence_types if "target" in item or "selected_" in item],
        rationale=rationale,
    )


def _score_arithmetic_error(evidence: DiagnosisEvidence) -> DiagnosisHypothesis:
    evidence_types = _evidence_types(evidence)
    score = 0.0
    rationale: list[str] = []

    if "step_value_mismatch" in evidence_types:
        score += 5.0
        rationale.append("step_value_mismatch")
    if "target_correct_but_value_wrong" in evidence_types:
        score += 4.0
        rationale.append("target_correct_but_value_wrong")
    if "final_answer_mismatch" in evidence_types and "target_ref_match" in evidence_types:
        score += 2.0
        rationale.append("final_answer_mismatch+target_ref_match")

    if "selected_intermediate_reference" in evidence_types or "selected_visible_problem_quantity" in evidence_types:
        score -= 4.0
    if "operation_mismatch" in evidence_types:
        score -= 2.0
    if "dependency_mismatch" in evidence_types:
        score -= 1.5
    if "correct_final_answer" in evidence_types:
        score -= 6.0

    subtype = "intermediate_calculation_error" if "step_value_mismatch" in evidence_types else "final_computation_error"
    localization = (
        ErrorLocalization.INTERMEDIATE_STEP
        if subtype == "intermediate_calculation_error" and evidence.first_divergence_step_id is not None
        else ErrorLocalization.FINAL_COMPUTATION
    )
    summary = (
        "The student appears to follow the right target but makes an incorrect intermediate calculation."
        if subtype == "intermediate_calculation_error"
        else "The student appears to target the right final quantity but lands on the wrong numeric result."
    )
    return DiagnosisHypothesis(
        label=DiagnosisLabel.ARITHMETIC_ERROR,
        subtype=subtype,
        localization=localization,
        summary=summary,
        score=score,
        supporting_evidence_types=[
            item for item in evidence_types if item in {"step_value_mismatch", "target_correct_but_value_wrong", "final_answer_mismatch"}
        ],
        rationale=rationale,
    )


def _score_quantity_relation_error(evidence: DiagnosisEvidence) -> DiagnosisHypothesis:
    evidence_types = _evidence_types(evidence)
    align_counts = _alignment_relationship_counts(evidence)
    score = 0.0
    rationale: list[str] = []

    subtype = "wrong_operation_or_relationship"
    summary = "The student appears to combine the quantities using the wrong relationship or operation."

    if "operation_mismatch" in evidence_types:
        score += 5.0
        rationale.append("operation_mismatch")

    if "dependency_mismatch" in evidence_types:
        score += 4.5
        rationale.append("dependency_mismatch")
        subtype = "missing_dependency_or_relationship"
        summary = "The student appears to connect intermediate quantities with the wrong dependency structure."

    if "edge_level_divergence" in evidence_types:
        score += 2.0
        rationale.append("edge_level_divergence")

    if "unsupported_student_step" in evidence_types:
        score += 2.0 if "correct_final_answer" in evidence_types else 1.5
        rationale.append("unsupported_student_step")

    if align_counts.get("dependency_mismatch", 0) > 0:
        score += 0.5
        rationale.append("alignment_dependency_mismatch")

    if "selected_intermediate_reference" in evidence_types or "selected_visible_problem_quantity" in evidence_types:
        score -= 3.0
    if "correct_final_answer" in evidence_types:
        if "reordered_but_consistent_steps" in evidence_types:
            score -= 5.0
        elif any(
            evidence_type in evidence_types
            for evidence_type in {"operation_mismatch", "dependency_mismatch", "unsupported_student_step"}
        ):
            score += 3.0
            subtype = "process_inconsistent_but_final_correct"
            summary = "The student's final answer is correct, but the recorded process is inconsistent with the canonical quantity relationships."

    return DiagnosisHypothesis(
        label=DiagnosisLabel.QUANTITY_RELATION_ERROR,
        subtype=subtype,
        localization=ErrorLocalization.COMBINING_QUANTITIES,
        summary=summary,
        score=score,
        supporting_evidence_types=[
            item
            for item in evidence_types
            if item in {"operation_mismatch", "dependency_mismatch", "edge_level_divergence", "unsupported_student_step"}
        ],
        rationale=rationale,
    )


def _score_unknown_error(evidence: DiagnosisEvidence) -> DiagnosisHypothesis:
    evidence_types = _evidence_types(evidence)
    score = 1.0
    rationale: list[str] = ["fallback_unknown"]
    if "final_answer_mismatch" in evidence_types:
        score += 1.5
        rationale.append("final_answer_mismatch")
    if "graph_edit_distance" in evidence_types and _graph_edit_cost(evidence) > 0:
        score += 1.0
        rationale.append("graph_edit_distance_nonzero")
    return DiagnosisHypothesis(
        label=DiagnosisLabel.UNKNOWN_ERROR,
        subtype="mismatch_without_clear_mechanism",
        localization=ErrorLocalization.UNKNOWN,
        summary="The student's answer does not match the canonical reference, but the available evidence is not specific enough to isolate the mechanism.",
        score=score,
        supporting_evidence_types=evidence_types,
        rationale=rationale,
    )


def build_diagnosis_hypotheses(evidence: DiagnosisEvidence) -> list[DiagnosisHypothesis]:
    hypotheses = [
        _score_correct_answer(evidence),
        _score_unparseable_answer(evidence),
        _score_target_misunderstanding(evidence),
        _score_arithmetic_error(evidence),
        _score_quantity_relation_error(evidence),
        _score_unknown_error(evidence),
    ]
    return sorted(hypotheses, key=lambda item: item.score, reverse=True)
