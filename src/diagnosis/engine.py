"""Diagnosis engine with intervention-oriented state estimation."""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from src.diagnosis.scoring import DiagnosisHypothesis, build_diagnosis_hypotheses
from src.evidence.builder import build_diagnosis_context
from src.llm import LLMClient, LLMGenerationError
from src.models import (
    AnswerAcceptability,
    CanonicalReference,
    DiagnosisContext,
    DiagnosisEvidence,
    DiagnosisLabel,
    DiagnosisResult,
    DiagnosisState,
    ErrorLocalization,
    FormalizedProblem,
    ProcessEquivalence,
    StudentWorkState,
    TargetAlignment,
)


_VERIFIED_ERROR_MECHANISMS = [
    "wrong_target_selected",
    "quantity_relationship_invalid",
    "arithmetic_execution_invalid",
    "answer_not_numeric",
]

_RELATION_EVIDENCE_TYPES = {
    "operation_mismatch",
    "dependency_mismatch",
    "alignment_dependency_mismatch",
    "edge_level_divergence",
}

_ARITHMETIC_EVIDENCE_TYPES = {
    "step_value_mismatch",
    "target_correct_but_value_wrong",
    "final_answer_mismatch",
}

_NOISY_PROCESS_EVIDENCE_TYPES = {
    "operation_mismatch",
    "dependency_mismatch",
    "alignment_dependency_mismatch",
    "edge_level_divergence",
    "unsupported_student_step",
}


def _sanitize_error_text(text: str, limit: int = 320) -> str:
    compact = " ".join(text.split())
    compact = compact.replace("\n", " ").replace("\r", " ")
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _classify_diagnosis_exception(exc: Exception) -> tuple[str, str]:
    message = _sanitize_error_text(str(exc))
    if isinstance(exc, LLMGenerationError):
        lowered = message.lower()
        if "request failed" in lowered:
            return "transport", message
        if "response shape was invalid" in lowered:
            return "response_shape", message
        if (
            "empty content" in lowered
            or "valid json object" in lowered
            or "json response must be an object" in lowered
        ):
            return "response_payload", message
        return "llm_generation", message

    if isinstance(exc, ValidationError):
        return "schema_validation", message

    if isinstance(exc, ValueError):
        lowered = message.lower()
        if lowered.startswith("diagnosis_state_validation_failed:"):
            return "schema_validation", message
        if lowered.startswith("diagnosis_result_projection_failed:"):
            return "projection", message
        if lowered.startswith("diagnosis_semantic_guard_failed:"):
            return "semantic_guard", message
        return "value_error", message

    if isinstance(exc, TypeError):
        return "type_error", message

    return "unknown", message


def _evidence_types(evidence: DiagnosisEvidence) -> list[str]:
    return [item.evidence_type for item in evidence.evidence_items]


def _supporting_types_from_grounded(grounded_evidence: Any) -> list[str]:
    if grounded_evidence is None:
        return []
    if isinstance(grounded_evidence, dict):
        evidence_types = grounded_evidence.get("evidence_types")
        if isinstance(evidence_types, list):
            return [str(item) for item in evidence_types if isinstance(item, str)]
        items = grounded_evidence.get("items")
        if isinstance(items, list):
            extracted: list[str] = []
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("type"), str):
                    extracted.append(item["type"])
            return extracted
        return []
    if isinstance(grounded_evidence, list):
        extracted: list[str] = []
        for item in grounded_evidence:
            if isinstance(item, str):
                extracted.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("type"), str):
                    extracted.append(item["type"])
                elif isinstance(item.get("evidence_type"), str):
                    extracted.append(item["evidence_type"])
        return extracted
    return []


def _diagnosis_target_step_id(hypothesis: DiagnosisHypothesis, evidence: DiagnosisEvidence) -> str | None:
    if evidence.first_divergence_step_id is None:
        return None
    if hypothesis.localization in {ErrorLocalization.NONE, ErrorLocalization.UNKNOWN}:
        return None
    return evidence.first_divergence_step_id


def _answer_acceptability(evidence_types: set[str]) -> AnswerAcceptability:
    if "unparseable_answer" in evidence_types:
        return AnswerAcceptability.UNPARSEABLE
    if "correct_final_answer" in evidence_types:
        return AnswerAcceptability.ACCEPTABLE
    return AnswerAcceptability.UNACCEPTABLE


def _target_alignment(evidence_types: set[str], answer_acceptability: AnswerAcceptability) -> TargetAlignment:
    if "selected_intermediate_reference" in evidence_types or "selected_visible_problem_quantity" in evidence_types:
        return TargetAlignment.MISALIGNED
    if (
        "target_ref_match" in evidence_types
        or "target_correct_but_value_wrong" in evidence_types
        or answer_acceptability == AnswerAcceptability.ACCEPTABLE
    ):
        return TargetAlignment.ALIGNED
    return TargetAlignment.UNKNOWN


def _process_equivalence(
    evidence_types: set[str],
    answer_acceptability: AnswerAcceptability,
    target_alignment: TargetAlignment,
    best: DiagnosisHypothesis,
) -> ProcessEquivalence:
    if answer_acceptability == AnswerAcceptability.UNPARSEABLE:
        return ProcessEquivalence.UNKNOWN

    if answer_acceptability == AnswerAcceptability.ACCEPTABLE and target_alignment == TargetAlignment.ALIGNED:
        if "reordered_but_consistent_steps" in evidence_types:
            return ProcessEquivalence.EQUIVALENT_NONCANONICAL
        if any(evidence_type in evidence_types for evidence_type in _NOISY_PROCESS_EVIDENCE_TYPES):
            return ProcessEquivalence.PARTIAL_OR_NOISY_BUT_ACCEPTABLE
        return ProcessEquivalence.CANONICAL

    if target_alignment == TargetAlignment.MISALIGNED:
        return ProcessEquivalence.PARTIAL_OR_NOISY_BUT_ACCEPTABLE

    if best.label in {DiagnosisLabel.ARITHMETIC_ERROR, DiagnosisLabel.QUANTITY_RELATION_ERROR}:
        return ProcessEquivalence.INCONSISTENT

    return ProcessEquivalence.UNKNOWN


def _uncertain_concerns_from_evidence(
    evidence_types: set[str],
    process_equivalence: ProcessEquivalence,
    *,
    intervention_required: bool,
) -> list[str]:
    concerns: list[str] = []
    if process_equivalence == ProcessEquivalence.EQUIVALENT_NONCANONICAL:
        concerns.append("alternate_noncanonical_process")
    if process_equivalence == ProcessEquivalence.PARTIAL_OR_NOISY_BUT_ACCEPTABLE:
        concerns.append("partial_or_noisy_process")
    if "dependency_mismatch" in evidence_types or "alignment_dependency_mismatch" in evidence_types:
        concerns.append("dependency_noise")
    if "operation_mismatch" in evidence_types:
        concerns.append("operation_label_noise")
    if "unsupported_student_step" in evidence_types:
        concerns.append("unsupported_extra_steps")
    if not intervention_required and "edge_level_divergence" in evidence_types:
        concerns.append("structural_projection_mismatch")
    return list(dict.fromkeys(concerns))


def _deterministic_state_summary(
    answer_acceptability: AnswerAcceptability,
    target_alignment: TargetAlignment,
    process_equivalence: ProcessEquivalence,
    intervention_required: bool,
    verified_error_mechanisms: list[str],
) -> str:
    if answer_acceptability == AnswerAcceptability.UNPARSEABLE:
        return "The student's answer is not yet parseable into one clear target value."
    if not intervention_required and target_alignment == TargetAlignment.ALIGNED:
        if process_equivalence == ProcessEquivalence.CANONICAL:
            return "The student's answer is acceptable and aligned with the requested target."
        if process_equivalence == ProcessEquivalence.EQUIVALENT_NONCANONICAL:
            return "The student's answer is acceptable and target-aligned, using a different but valid process."
        return "The student's answer is acceptable and target-aligned, even though the recorded process is partial or noisy."
    if "wrong_target_selected" in verified_error_mechanisms:
        return "The student appears to be working with the wrong target quantity rather than the requested answer."
    if "quantity_relationship_invalid" in verified_error_mechanisms:
        return "The student's work needs intervention because the quantity relationship appears to be set up incorrectly."
    if "arithmetic_execution_invalid" in verified_error_mechanisms:
        return "The student's target appears aligned, but the computation needs to be checked."
    return "The student's work appears to need intervention, but the exact verified error mechanism is still unclear."


def _deterministic_diagnosis_state(evidence: DiagnosisEvidence) -> tuple[DiagnosisState, list[DiagnosisHypothesis]]:
    hypotheses = build_diagnosis_hypotheses(evidence)
    best = hypotheses[0]
    runner_up = hypotheses[1] if len(hypotheses) > 1 else None
    evidence_types = set(_evidence_types(evidence))

    answer_acceptability = _answer_acceptability(evidence_types)
    target_alignment = _target_alignment(evidence_types, answer_acceptability)
    process_equivalence = _process_equivalence(evidence_types, answer_acceptability, target_alignment, best)

    candidate_localization = ErrorLocalization.UNKNOWN
    candidate_target_step_id: str | None = None
    verified_error_mechanisms: list[str] = []

    if answer_acceptability == AnswerAcceptability.UNPARSEABLE:
        verified_error_mechanisms = ["answer_not_numeric"]
        candidate_localization = ErrorLocalization.UNKNOWN
        intervention_required = True
    elif target_alignment == TargetAlignment.MISALIGNED:
        verified_error_mechanisms = ["wrong_target_selected"]
        candidate_localization = ErrorLocalization.TARGET_SELECTION
        candidate_target_step_id = _diagnosis_target_step_id(best, evidence) or evidence.first_divergence_step_id
        intervention_required = True
    elif answer_acceptability == AnswerAcceptability.ACCEPTABLE and target_alignment == TargetAlignment.ALIGNED:
        verified_error_mechanisms = []
        candidate_localization = ErrorLocalization.NONE
        intervention_required = False
    else:
        relation_signal = any(evidence_type in evidence_types for evidence_type in _RELATION_EVIDENCE_TYPES)
        arithmetic_signal = any(evidence_type in evidence_types for evidence_type in _ARITHMETIC_EVIDENCE_TYPES)

        if relation_signal and not arithmetic_signal:
            verified_error_mechanisms = ["quantity_relationship_invalid"]
            candidate_localization = ErrorLocalization.COMBINING_QUANTITIES
            candidate_target_step_id = _diagnosis_target_step_id(best, evidence) or evidence.first_divergence_step_id
        elif arithmetic_signal and not relation_signal:
            verified_error_mechanisms = ["arithmetic_execution_invalid"]
            if "step_value_mismatch" in evidence_types:
                candidate_localization = ErrorLocalization.INTERMEDIATE_STEP
            else:
                candidate_localization = ErrorLocalization.FINAL_COMPUTATION
            candidate_target_step_id = _diagnosis_target_step_id(best, evidence) or evidence.first_divergence_step_id
        elif best.label == DiagnosisLabel.QUANTITY_RELATION_ERROR:
            verified_error_mechanisms = ["quantity_relationship_invalid"]
            candidate_localization = (
                best.localization
                if best.localization not in {ErrorLocalization.NONE, ErrorLocalization.UNKNOWN}
                else ErrorLocalization.COMBINING_QUANTITIES
            )
            candidate_target_step_id = _diagnosis_target_step_id(best, evidence) or evidence.first_divergence_step_id
        elif best.label == DiagnosisLabel.ARITHMETIC_ERROR:
            verified_error_mechanisms = ["arithmetic_execution_invalid"]
            candidate_localization = (
                best.localization
                if best.localization not in {ErrorLocalization.NONE, ErrorLocalization.UNKNOWN}
                else ErrorLocalization.INTERMEDIATE_STEP
                if "step_value_mismatch" in evidence_types
                else ErrorLocalization.FINAL_COMPUTATION
            )
            candidate_target_step_id = _diagnosis_target_step_id(best, evidence) or evidence.first_divergence_step_id
        else:
            verified_error_mechanisms = []
            candidate_localization = (
                best.localization
                if best.localization not in {ErrorLocalization.NONE}
                else ErrorLocalization.UNKNOWN
            )
            candidate_target_step_id = _diagnosis_target_step_id(best, evidence) or evidence.first_divergence_step_id

        intervention_required = True

    notes = list(evidence.notes)
    notes.append(f"diagnosis_top_hypothesis={best.label.value}:{best.score:.2f}")
    if runner_up is not None:
        margin = best.score - runner_up.score
        notes.append(f"diagnosis_runner_up={runner_up.label.value}:{runner_up.score:.2f}")
        notes.append(f"diagnosis_margin={margin:.2f}")
        if margin < 1.0 and best.label != DiagnosisLabel.CORRECT_ANSWER:
            notes.append("diagnosis_ambiguous_competing_hypotheses")
            if best.label == DiagnosisLabel.UNKNOWN_ERROR:
                notes.append("diagnosis_low_separation_unknown")
    for reason in best.rationale:
        notes.append(f"diagnosis_rationale:{reason}")

    uncertain_concerns = _uncertain_concerns_from_evidence(
        evidence_types,
        process_equivalence,
        intervention_required=intervention_required,
    )
    if intervention_required and not verified_error_mechanisms:
        uncertain_concerns.append("unclear_intervention_mechanism")
    if target_alignment == TargetAlignment.MISALIGNED and candidate_target_step_id is None:
        uncertain_concerns.append("missing_target_step_grounding")
    uncertain_concerns = list(dict.fromkeys(uncertain_concerns))

    summary = _deterministic_state_summary(
        answer_acceptability,
        target_alignment,
        process_equivalence,
        intervention_required,
        verified_error_mechanisms,
    )
    confidence = min(max(evidence.confidence + min(best.score / 20.0, 0.12), 0.35), 0.98)
    candidate_focus_step_ids = [candidate_target_step_id] if candidate_target_step_id is not None else []

    return (
        DiagnosisState(
            answer_acceptability=answer_acceptability,
            target_alignment=target_alignment,
            process_equivalence=process_equivalence,
            intervention_required=intervention_required,
            verified_error_mechanisms=verified_error_mechanisms,
            uncertain_concerns=uncertain_concerns,
            candidate_localization=candidate_localization,
            candidate_target_step_id=candidate_target_step_id,
            candidate_focus_step_ids=candidate_focus_step_ids,
            supporting_evidence_types=best.supporting_evidence_types or list(evidence_types),
            grounded_evidence={
                "evidence_types": best.supporting_evidence_types or list(evidence_types),
                "first_divergence_step_id": evidence.first_divergence_step_id,
            },
            key_findings=[summary],
            summary=summary,
            confidence=confidence,
            notes=notes,
        ),
        hypotheses,
    )


def _project_state_to_result(
    state: DiagnosisState,
    evidence: DiagnosisEvidence,
    *,
    used_llm_first: bool,
) -> DiagnosisResult:
    supporting_evidence_types = list(state.supporting_evidence_types)
    if not supporting_evidence_types:
        supporting_evidence_types = _supporting_types_from_grounded(state.grounded_evidence)
    if not supporting_evidence_types:
        supporting_evidence_types = _evidence_types(evidence)

    mechanisms = set(state.verified_error_mechanisms)

    if state.answer_acceptability == AnswerAcceptability.UNPARSEABLE:
        label = DiagnosisLabel.UNPARSEABLE_ANSWER
        localization = ErrorLocalization.UNKNOWN
        subtype = "answer_not_numeric"
        target_step_id = None
    elif (
        not state.intervention_required
        and state.answer_acceptability == AnswerAcceptability.ACCEPTABLE
        and state.target_alignment == TargetAlignment.ALIGNED
    ):
        label = DiagnosisLabel.CORRECT_ANSWER
        localization = ErrorLocalization.NONE
        subtype = "none"
        target_step_id = None
    elif state.target_alignment == TargetAlignment.MISALIGNED or "wrong_target_selected" in mechanisms:
        label = DiagnosisLabel.TARGET_MISUNDERSTANDING
        localization = ErrorLocalization.TARGET_SELECTION
        subtype = (
            "selected_visible_problem_quantity"
            if "selected_visible_problem_quantity" in supporting_evidence_types
            else "selected_intermediate_quantity"
            if "selected_intermediate_reference" in supporting_evidence_types
            else "wrong_target_selected"
        )
        target_step_id = state.candidate_target_step_id or evidence.first_divergence_step_id
    elif "quantity_relationship_invalid" in mechanisms:
        label = DiagnosisLabel.QUANTITY_RELATION_ERROR
        localization = (
            state.candidate_localization
            if state.candidate_localization not in {ErrorLocalization.NONE, ErrorLocalization.UNKNOWN}
            else ErrorLocalization.COMBINING_QUANTITIES
        )
        subtype = (
            "missing_dependency_or_relationship"
            if "dependency_mismatch" in supporting_evidence_types
            or "alignment_dependency_mismatch" in supporting_evidence_types
            else "wrong_operation_or_relationship"
        )
        target_step_id = state.candidate_target_step_id or evidence.first_divergence_step_id
    elif "arithmetic_execution_invalid" in mechanisms:
        label = DiagnosisLabel.ARITHMETIC_ERROR
        localization = (
            state.candidate_localization
            if state.candidate_localization not in {ErrorLocalization.NONE, ErrorLocalization.UNKNOWN}
            else ErrorLocalization.INTERMEDIATE_STEP
            if "step_value_mismatch" in supporting_evidence_types
            else ErrorLocalization.FINAL_COMPUTATION
        )
        subtype = (
            "intermediate_calculation_error"
            if localization == ErrorLocalization.INTERMEDIATE_STEP
            else "final_computation_error"
        )
        target_step_id = state.candidate_target_step_id or evidence.first_divergence_step_id
    else:
        label = DiagnosisLabel.UNKNOWN_ERROR
        localization = (
            state.candidate_localization
            if state.candidate_localization not in {ErrorLocalization.NONE}
            else ErrorLocalization.UNKNOWN
        )
        subtype = "intervention_needed_but_mechanism_unverified"
        target_step_id = (
            state.candidate_target_step_id or evidence.first_divergence_step_id
            if localization not in {ErrorLocalization.NONE, ErrorLocalization.UNKNOWN}
            else None
        )

    if localization in {ErrorLocalization.NONE, ErrorLocalization.UNKNOWN}:
        target_step_id = None

    confidence = state.confidence if state.confidence > 0 else max(evidence.confidence, 0.55)
    confidence = min(max(confidence, 0.2), 0.98)

    notes = list(state.notes)
    if used_llm_first:
        notes.append("llm_first_diagnosis_used")
    notes.append(f"diagnosis_state_answer_acceptability={state.answer_acceptability.value}")
    notes.append(f"diagnosis_state_target_alignment={state.target_alignment.value}")
    notes.append(f"diagnosis_state_process_equivalence={state.process_equivalence.value}")
    notes.append(f"diagnosis_state_intervention_required={str(state.intervention_required).lower()}")
    if state.verified_error_mechanisms:
        notes.append(
            "diagnosis_state_verified_error_mechanisms="
            + ",".join(sorted(set(state.verified_error_mechanisms)))
        )
    if state.uncertain_concerns:
        notes.append(
            "diagnosis_state_uncertain_concerns="
            + ",".join(sorted(set(state.uncertain_concerns)))
        )
    if state.candidate_target_step_id is not None:
        notes.append(f"diagnosis_state_candidate_target_step_id={state.candidate_target_step_id}")
    for finding in state.key_findings[:6]:
        cleaned = _sanitize_error_text(str(finding), limit=140)
        if cleaned:
            notes.append(f"diagnosis_finding:{cleaned}")

    try:
        return DiagnosisResult(
            diagnosis_label=label,
            subtype=subtype,
            localization=localization,
            target_step_id=target_step_id,
            summary=state.summary,
            supporting_evidence_types=supporting_evidence_types,
            confidence=confidence,
            notes=notes,
        )
    except ValidationError as exc:
        raise ValueError(
            f"diagnosis_result_projection_failed: {exc.errors(include_url=False)}"
        ) from exc


def _state_prompt_context(context: DiagnosisContext) -> dict[str, Any]:
    return context.model_dump(mode="json")


def _llm_build_diagnosis_state(
    evidence: DiagnosisEvidence,
    context: DiagnosisContext,
    llm_client: LLMClient,
) -> DiagnosisState:
    system_prompt = (
        "You are the intervention diagnosis state module for a math tutoring system. "
        "Return only a JSON object matching DiagnosisState. "
        "DiagnosisEvidence is a factual forensic record. DiagnosisContext is compact supporting context. "
        "Your job is to estimate the student's current tutoring state, not to force every case into an error."
    )
    user_prompt = (
        "Allowed answer_acceptability values: "
        f"{[status.value for status in AnswerAcceptability]}\n"
        "Allowed target_alignment values: "
        f"{[status.value for status in TargetAlignment]}\n"
        "Allowed process_equivalence values: "
        f"{[status.value for status in ProcessEquivalence]}\n"
        "Allowed candidate_localization values: "
        f"{[label.value for label in ErrorLocalization]}\n"
        "Allowed verified_error_mechanisms values: "
        f"{_VERIFIED_ERROR_MECHANISMS}\n\n"
        "Return a DiagnosisState JSON object with exactly these fields:\n"
        "- answer_acceptability\n"
        "- target_alignment\n"
        "- process_equivalence\n"
        "- intervention_required\n"
        "- verified_error_mechanisms\n"
        "- uncertain_concerns\n"
        "- candidate_localization\n"
        "- candidate_target_step_id\n"
        "- candidate_focus_step_ids\n"
        "- supporting_evidence_types\n"
        "- grounded_evidence\n"
        "- key_findings\n"
        "- summary\n"
        "- confidence\n"
        "- notes\n\n"
        "Interpretation procedure:\n"
        "1. First decide whether any corrective intervention is required at all.\n"
        "2. Then decide whether the student's current answer is acceptable for tutoring purposes.\n"
        "3. Then decide whether the student is aligned with the requested target quantity.\n"
        "4. Only after that decide whether there is any verified error mechanism.\n\n"
        "Critical rules:\n"
        "- if the student's final answer is acceptable and aligned with the requested target, set intervention_required=false even when the process is alternate, reordered, split, merged, partial, or noisy\n"
        "- do not invent verified_error_mechanisms just because the process differs from the canonical one\n"
        "- use uncertain_concerns for plausible worries that are not yet verified\n"
        "- when intervention_required=false, verified_error_mechanisms must be empty\n"
        "- use quantity_relationship_invalid only when the student truly sets up or combines quantities with the wrong relationship, not merely a different but equivalent decomposition\n"
        "- use arithmetic_execution_invalid only when the setup/target are basically right but the numeric computation is wrong\n"
        "- use wrong_target_selected only when the student stops at or reasons toward a visible quantity or intermediate quantity instead of the requested target\n"
        "- candidate_localization and candidate_target_step_id are optional; use them only when they would ground a real intervention focus\n"
        "- summary must describe the student's current state, not assume there is an error\n\n"
        "DiagnosisEvidence:\n"
        f"{json.dumps(evidence.model_dump(mode='json'), ensure_ascii=True)}\n\n"
        "DiagnosisContext:\n"
        f"{json.dumps(_state_prompt_context(context), ensure_ascii=True)}\n\n"
        "Do not output fields outside DiagnosisState."
    )
    payload = llm_client.generate_json(
        task_name="diagnosis_state",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=6000,
    )
    try:
        return DiagnosisState.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(
            f"diagnosis_state_validation_failed: {exc.errors(include_url=False)}"
        ) from exc


def build_diagnosis(
    evidence: DiagnosisEvidence,
    *,
    context: DiagnosisContext | None = None,
    problem: FormalizedProblem | None = None,
    reference: CanonicalReference | None = None,
    student: StudentWorkState | None = None,
    llm_client: LLMClient | None = None,
) -> tuple[DiagnosisState, DiagnosisResult]:
    """Build both the internal diagnosis state and the public diagnosis result."""
    if context is None and problem is not None and reference is not None and student is not None:
        context = build_diagnosis_context(problem, reference, student, evidence)

    if llm_client is not None and context is not None:
        try:
            state = _llm_build_diagnosis_state(evidence, context, llm_client)
            result = _project_state_to_result(state, evidence, used_llm_first=True)
            evidence_types = set(_evidence_types(evidence))
            if "unparseable_answer" in evidence_types and state.answer_acceptability != AnswerAcceptability.UNPARSEABLE:
                raise ValueError(
                    "diagnosis_semantic_guard_failed: unparseable_answer evidence conflicts with diagnosis state"
                )
            return state, result
        except (LLMGenerationError, ValidationError, ValueError, TypeError, KeyError) as exc:
            failure_stage, failure_reason = _classify_diagnosis_exception(exc)
            deterministic_state, _ = _deterministic_diagnosis_state(evidence)
            deterministic_result = _project_state_to_result(
                deterministic_state,
                evidence,
                used_llm_first=False,
            )
            state_notes = list(deterministic_state.notes)
            state_notes.append("llm_diagnosis_failed_fallback")
            state_notes.append(f"llm_diagnosis_failure_stage:{failure_stage}")
            state_notes.append(f"llm_diagnosis_failure_reason:{failure_reason}")
            deterministic_state = deterministic_state.model_copy(update={"notes": state_notes})

            result_notes = list(deterministic_result.notes)
            result_notes.append("llm_diagnosis_failed_fallback")
            result_notes.append(f"llm_diagnosis_failure_stage:{failure_stage}")
            result_notes.append(f"llm_diagnosis_failure_reason:{failure_reason}")
            deterministic_result = deterministic_result.model_copy(update={"notes": result_notes})
            return deterministic_state, deterministic_result

    deterministic_state, _ = _deterministic_diagnosis_state(evidence)
    return deterministic_state, _project_state_to_result(
        deterministic_state,
        evidence,
        used_llm_first=False,
    )


def diagnose(
    evidence: DiagnosisEvidence,
    *,
    context: DiagnosisContext | None = None,
    problem: FormalizedProblem | None = None,
    reference: CanonicalReference | None = None,
    student: StudentWorkState | None = None,
    llm_client: LLMClient | None = None,
) -> DiagnosisResult:
    """Backward-compatible wrapper that returns only the public diagnosis result."""
    _, result = build_diagnosis(
        evidence,
        context=context,
        problem=problem,
        reference=reference,
        student=student,
        llm_client=llm_client,
    )
    return result
