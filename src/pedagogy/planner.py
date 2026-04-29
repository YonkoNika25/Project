"""Pedagogy planner built around an intermediate PedagogyState artifact."""
from __future__ import annotations

import json

from pydantic import ValidationError

from src.llm import LLMClient, LLMGenerationError
from src.models import (
    AnswerAcceptability,
    CanonicalReference,
    DiagnosisResult,
    DiagnosisState,
    DisclosurePolicy,
    ErrorLocalization,
    FormalizedProblem,
    HintLevel,
    HintPlan,
    HintStrategy,
    InterventionPosture,
    PedagogicalObjective,
    PedagogyState,
    ProcessEquivalence,
    StepGroundingRequirement,
    TeacherMove,
    TargetAlignment,
)


def _find_reference_step(reference: CanonicalReference, step_id: str | None):
    if step_id is None:
        return None
    return next((step for step in reference.chosen_plan.steps if step.step_id == step_id), None)


def _base_must_not_reveal(reference: CanonicalReference) -> list[str]:
    return ["final answer", f"{reference.final_answer:g}"]


def _step_specific_must_not_reveal(reference: CanonicalReference, step_id: str | None) -> list[str]:
    if step_id is None:
        return []

    hidden: list[str] = []
    for step, result in zip(reference.chosen_plan.steps, reference.execution_trace.step_results):
        if step.step_id == step_id and result.success and result.output_value is not None:
            hidden.extend([step.output_ref, f"{result.output_value:g}"])
            break
    return hidden


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _target_prompt(problem: FormalizedProblem) -> str:
    if problem.target is not None and problem.target.surface_text.strip():
        return problem.target.surface_text.rstrip("?")
    return "the quantity the question asks for"


def _candidate_target_step_id(diagnosis: DiagnosisResult, diagnosis_state: DiagnosisState) -> str | None:
    return diagnosis.target_step_id or diagnosis_state.candidate_target_step_id


def _planning_prompt_context(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
) -> dict[str, object]:
    candidate_step_id = _candidate_target_step_id(diagnosis, diagnosis_state)
    target_step = _find_reference_step(reference, candidate_step_id)
    return {
        "problem_target": problem.target.surface_text if problem.target is not None else None,
        "diagnosis_state": diagnosis_state.model_dump(mode="json"),
        "public_diagnosis": diagnosis.model_dump(mode="json"),
        "candidate_target_step": (
            {
                "step_id": target_step.step_id,
                "operation": target_step.operation.value,
                "output_ref": target_step.output_ref,
                "explanation": target_step.explanation,
            }
            if target_step is not None
            else None
        ),
        "always_hide": _base_must_not_reveal(reference),
        "step_specific_hidden": _step_specific_must_not_reveal(reference, candidate_step_id),
    }


def _coarse_state_from_result(diagnosis: DiagnosisResult) -> DiagnosisState:
    if diagnosis.diagnosis_label.value == "correct_answer":
        return DiagnosisState(
            answer_acceptability=AnswerAcceptability.ACCEPTABLE,
            target_alignment=TargetAlignment.ALIGNED,
            process_equivalence=ProcessEquivalence.UNKNOWN,
            intervention_required=False,
            verified_error_mechanisms=[],
            uncertain_concerns=[],
            candidate_localization=ErrorLocalization.NONE,
            candidate_target_step_id=None,
            candidate_focus_step_ids=[],
            supporting_evidence_types=list(diagnosis.supporting_evidence_types),
            grounded_evidence=None,
            key_findings=[diagnosis.summary],
            summary=diagnosis.summary,
            confidence=diagnosis.confidence,
            notes=["coarse_state_from_diagnosis_result"],
        )
    if diagnosis.diagnosis_label.value == "unparseable_answer":
        return DiagnosisState(
            answer_acceptability=AnswerAcceptability.UNPARSEABLE,
            target_alignment=TargetAlignment.UNKNOWN,
            process_equivalence=ProcessEquivalence.UNKNOWN,
            intervention_required=True,
            verified_error_mechanisms=["answer_not_numeric"],
            uncertain_concerns=[],
            candidate_localization=ErrorLocalization.UNKNOWN,
            candidate_target_step_id=None,
            candidate_focus_step_ids=[],
            supporting_evidence_types=list(diagnosis.supporting_evidence_types),
            grounded_evidence=None,
            key_findings=[diagnosis.summary],
            summary=diagnosis.summary,
            confidence=diagnosis.confidence,
            notes=["coarse_state_from_diagnosis_result"],
        )
    if diagnosis.diagnosis_label.value == "target_misunderstanding":
        return DiagnosisState(
            answer_acceptability=AnswerAcceptability.UNACCEPTABLE,
            target_alignment=TargetAlignment.MISALIGNED,
            process_equivalence=ProcessEquivalence.PARTIAL_OR_NOISY_BUT_ACCEPTABLE,
            intervention_required=True,
            verified_error_mechanisms=["wrong_target_selected"],
            uncertain_concerns=[],
            candidate_localization=ErrorLocalization.TARGET_SELECTION,
            candidate_target_step_id=diagnosis.target_step_id,
            candidate_focus_step_ids=[diagnosis.target_step_id] if diagnosis.target_step_id else [],
            supporting_evidence_types=list(diagnosis.supporting_evidence_types),
            grounded_evidence=None,
            key_findings=[diagnosis.summary],
            summary=diagnosis.summary,
            confidence=diagnosis.confidence,
            notes=["coarse_state_from_diagnosis_result"],
        )
    if diagnosis.diagnosis_label.value == "quantity_relation_error":
        return DiagnosisState(
            answer_acceptability=AnswerAcceptability.UNACCEPTABLE,
            target_alignment=TargetAlignment.ALIGNED,
            process_equivalence=ProcessEquivalence.INCONSISTENT,
            intervention_required=True,
            verified_error_mechanisms=["quantity_relationship_invalid"],
            uncertain_concerns=[],
            candidate_localization=diagnosis.localization,
            candidate_target_step_id=diagnosis.target_step_id,
            candidate_focus_step_ids=[diagnosis.target_step_id] if diagnosis.target_step_id else [],
            supporting_evidence_types=list(diagnosis.supporting_evidence_types),
            grounded_evidence=None,
            key_findings=[diagnosis.summary],
            summary=diagnosis.summary,
            confidence=diagnosis.confidence,
            notes=["coarse_state_from_diagnosis_result"],
        )
    return DiagnosisState(
        answer_acceptability=AnswerAcceptability.UNACCEPTABLE,
        target_alignment=TargetAlignment.ALIGNED,
        process_equivalence=ProcessEquivalence.INCONSISTENT,
        intervention_required=True,
        verified_error_mechanisms=["arithmetic_execution_invalid"],
        uncertain_concerns=[],
        candidate_localization=diagnosis.localization,
        candidate_target_step_id=diagnosis.target_step_id,
        candidate_focus_step_ids=[diagnosis.target_step_id] if diagnosis.target_step_id else [],
        supporting_evidence_types=list(diagnosis.supporting_evidence_types),
        grounded_evidence=None,
        key_findings=[diagnosis.summary],
        summary=diagnosis.summary,
        confidence=diagnosis.confidence,
        notes=["coarse_state_from_diagnosis_result"],
    )


def _focus_for_target_refocus(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
) -> list[str]:
    target_prompt = _target_prompt(problem)
    target_step_id = _candidate_target_step_id(diagnosis, diagnosis_state)
    step = _find_reference_step(reference, target_step_id)
    focus_points = ["what quantity the question is actually asking for", target_prompt]
    if step is not None:
        focus_points.append(f"why {step.output_ref} is not the final requested quantity")
        if step.explanation:
            focus_points.append(step.explanation)
    return _dedupe(focus_points)


def _focus_for_relationship(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
) -> list[str]:
    target_prompt = _target_prompt(problem)
    target_step_id = _candidate_target_step_id(diagnosis, diagnosis_state)
    step = _find_reference_step(reference, target_step_id)
    focus_points = ["how the problem quantities should be related", f"target: {target_prompt}"]
    if step is not None and step.explanation:
        focus_points.append(step.explanation)
    return _dedupe(focus_points)


def _focus_for_arithmetic(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
) -> list[str]:
    target_prompt = _target_prompt(problem)
    target_step_id = _candidate_target_step_id(diagnosis, diagnosis_state)
    step = _find_reference_step(reference, target_step_id)
    focus_points = [f"target: {target_prompt}"]
    if diagnosis_state.candidate_localization == ErrorLocalization.INTERMEDIATE_STEP and step is not None:
        focus_points.append("recompute the arithmetic carefully")
        focus_points.append(f"check the calculation around {step.output_ref}")
        if step.explanation:
            focus_points.append(step.explanation)
    else:
        focus_points.append("revisit the final computation after setting up the right quantities")
    return _dedupe(focus_points)


def _llm_build_pedagogy_state(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
    llm_client: LLMClient,
) -> PedagogyState:
    system_prompt = (
        "You are the pedagogy planning module for a math tutor. "
        "Return only a JSON object matching PedagogyState. "
        "Decide the pedagogical truth first; do not jump directly to teacher moves."
    )
    user_prompt = (
        f"Allowed intervention_posture values: {[value.value for value in InterventionPosture]}\n"
        f"Allowed primary_objective values: {[value.value for value in PedagogicalObjective]}\n"
        f"Allowed disclosure_policy values: {[value.value for value in DisclosurePolicy]}\n"
        f"Allowed step_grounding_requirement values: {[value.value for value in StepGroundingRequirement]}\n\n"
        "Return a PedagogyState JSON object with exactly these fields:\n"
        "- intervention_posture\n"
        "- primary_objective\n"
        "- disclosure_policy\n"
        "- step_grounding_requirement\n"
        "- candidate_target_step_id\n"
        "- candidate_focus_step_ids\n"
        "- focus_semantics\n"
        "- uncertain_pedagogical_concerns\n"
        "- pedagogical_goal\n"
        "- student_action\n"
        "- rationale\n"
        "- confidence\n"
        "- notes\n\n"
        "Planning rules:\n"
        "- start by deciding whether any intervention is needed at all\n"
        "- if the answer is acceptable, aligned to the target, and no verified error mechanism exists, prefer intervention_posture=acknowledge_correct\n"
        "- use intervention_posture=reflective_optional only for light, non-corrective reinforcement; do not use it to smuggle in correction\n"
        "- use intervention_posture=corrective only when the tutoring state actually needs correction or clarification\n"
        "- primary_objective=clarify_answer_format for unparseable answers or answer-format problems\n"
        "- primary_objective=refocus_target when the student is focused on the wrong quantity or wrong target\n"
        "- primary_objective=repair_quantity_relationship when quantity relationship setup is the verified problem\n"
        "- primary_objective=recompute_arithmetic only when the target is aligned and arithmetic execution is the verified problem\n"
        "- primary_objective=reinforce_understanding is for optional reflection on acceptable work, not for correction\n"
        "- primary_objective=clarify_state is only for uncertain corrective situations when a verified mechanism is still missing\n"
        "- disclosure_policy should be none/low/medium based on how explicit the next hint may be; none means do not introduce new content\n"
        "- step_grounding_requirement is none unless the intervention really needs a canonical step anchor\n"
        "- focus_semantics should describe conceptual focuses, not hidden answers, exact protected values, or final answer strings\n"
        "- uncertain_pedagogical_concerns should hold open concerns, not verified errors\n"
        "- keep pedagogical_goal and rationale short and concrete\n\n"
        f"PlanningContext:\n{json.dumps(_planning_prompt_context(problem, reference, diagnosis, diagnosis_state), ensure_ascii=True)}\n\n"
        "Do not output fields outside PedagogyState."
    )
    payload = llm_client.generate_json(
        task_name="pedagogy_state",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=6000,
    )
    try:
        return PedagogyState.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"pedagogy_state_validation_failed: {exc.errors(include_url=False)}") from exc


def _deterministic_pedagogy_state(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
) -> PedagogyState:
    target_step_id = _candidate_target_step_id(diagnosis, diagnosis_state)
    mechanisms = set(diagnosis_state.verified_error_mechanisms)
    concerns = list(diagnosis_state.uncertain_concerns)

    if (
        not diagnosis_state.intervention_required
        and diagnosis_state.answer_acceptability == AnswerAcceptability.ACCEPTABLE
        and diagnosis_state.target_alignment == TargetAlignment.ALIGNED
    ):
        return PedagogyState(
            intervention_posture=InterventionPosture.ACKNOWLEDGE_CORRECT,
            primary_objective=PedagogicalObjective.NONE,
            disclosure_policy=DisclosurePolicy.NONE,
            step_grounding_requirement=StepGroundingRequirement.NONE,
            candidate_target_step_id=None,
            candidate_focus_step_ids=[],
            focus_semantics=[],
            uncertain_pedagogical_concerns=concerns,
            pedagogical_goal="Acknowledge that the student's current answer is already acceptable.",
            student_action=None,
            rationale="No corrective intervention is needed when the answer is acceptable and aligned to the target.",
            confidence=min(diagnosis.confidence, 0.95),
            notes=["deterministic_pedagogy_state"],
        )

    if diagnosis_state.answer_acceptability == AnswerAcceptability.UNPARSEABLE:
        return PedagogyState(
            intervention_posture=InterventionPosture.CORRECTIVE,
            primary_objective=PedagogicalObjective.CLARIFY_ANSWER_FORMAT,
            disclosure_policy=DisclosurePolicy.LOW,
            step_grounding_requirement=StepGroundingRequirement.NONE,
            candidate_target_step_id=None,
            candidate_focus_step_ids=[],
            focus_semantics=[
                f"what quantity the question asks for: {_target_prompt(problem)}",
                "state one clear numeric answer",
            ],
            uncertain_pedagogical_concerns=concerns,
            pedagogical_goal="Help the student restate the target and provide one parseable numeric answer.",
            student_action="Restate the question in your own words and then give one clear number.",
            rationale="Answer-format clarity comes before deeper remediation when the response is not parseable.",
            confidence=min(diagnosis.confidence + 0.02, 0.96),
            notes=["deterministic_pedagogy_state"],
        )

    if diagnosis_state.target_alignment == TargetAlignment.MISALIGNED or "wrong_target_selected" in mechanisms:
        step_requirement = (
            StepGroundingRequirement.OPTIONAL if target_step_id is not None else StepGroundingRequirement.NONE
        )
        return PedagogyState(
            intervention_posture=InterventionPosture.CORRECTIVE,
            primary_objective=PedagogicalObjective.REFOCUS_TARGET,
            disclosure_policy=DisclosurePolicy.LOW,
            step_grounding_requirement=step_requirement,
            candidate_target_step_id=target_step_id,
            candidate_focus_step_ids=[target_step_id] if target_step_id else [],
            focus_semantics=_focus_for_target_refocus(problem, reference, diagnosis, diagnosis_state),
            uncertain_pedagogical_concerns=concerns,
            pedagogical_goal="Redirect the student from the wrong quantity back to the requested target.",
            student_action="Compare your current result to the quantity named in the question.",
            rationale="The main issue is target selection, so the next intervention should refocus the student before any computation advice.",
            confidence=min(diagnosis.confidence + 0.03, 0.97),
            notes=["deterministic_pedagogy_state"],
        )

    if "quantity_relationship_invalid" in mechanisms:
        step_requirement = (
            StepGroundingRequirement.REQUIRED if target_step_id is not None else StepGroundingRequirement.OPTIONAL
        )
        return PedagogyState(
            intervention_posture=InterventionPosture.CORRECTIVE,
            primary_objective=PedagogicalObjective.REPAIR_QUANTITY_RELATIONSHIP,
            disclosure_policy=DisclosurePolicy.MEDIUM,
            step_grounding_requirement=step_requirement,
            candidate_target_step_id=target_step_id,
            candidate_focus_step_ids=[target_step_id] if target_step_id else [],
            focus_semantics=_focus_for_relationship(problem, reference, diagnosis, diagnosis_state),
            uncertain_pedagogical_concerns=concerns,
            pedagogical_goal="Repair how the student relates the quantities before recomputing.",
            student_action="Rebuild the relationship between the quantities before calculating again.",
            rationale="Relationship errors should be addressed before arithmetic, otherwise the student recomputes the wrong setup.",
            confidence=min(diagnosis.confidence + 0.02, 0.97),
            notes=["deterministic_pedagogy_state"],
        )

    if "arithmetic_execution_invalid" in mechanisms:
        step_requirement = (
            StepGroundingRequirement.REQUIRED if target_step_id is not None else StepGroundingRequirement.OPTIONAL
        )
        return PedagogyState(
            intervention_posture=InterventionPosture.CORRECTIVE,
            primary_objective=PedagogicalObjective.RECOMPUTE_ARITHMETIC,
            disclosure_policy=DisclosurePolicy.LOW,
            step_grounding_requirement=step_requirement,
            candidate_target_step_id=target_step_id,
            candidate_focus_step_ids=[target_step_id] if target_step_id else [],
            focus_semantics=_focus_for_arithmetic(problem, reference, diagnosis, diagnosis_state),
            uncertain_pedagogical_concerns=concerns,
            pedagogical_goal="Preserve the setup and get the student to recompute the suspect arithmetic step.",
            student_action="Rewrite the relevant calculation carefully before moving on.",
            rationale="The state suggests the student is close enough that a targeted recomputation prompt is safer than reteaching the whole setup.",
            confidence=min(diagnosis.confidence + 0.03, 0.97),
            notes=["deterministic_pedagogy_state"],
        )

    if (
        diagnosis_state.answer_acceptability == AnswerAcceptability.ACCEPTABLE
        and diagnosis_state.target_alignment == TargetAlignment.ALIGNED
    ):
        return PedagogyState(
            intervention_posture=InterventionPosture.REFLECTIVE_OPTIONAL,
            primary_objective=PedagogicalObjective.REINFORCE_UNDERSTANDING,
            disclosure_policy=DisclosurePolicy.NONE,
            step_grounding_requirement=StepGroundingRequirement.NONE,
            candidate_target_step_id=None,
            candidate_focus_step_ids=[],
            focus_semantics=[],
            uncertain_pedagogical_concerns=concerns,
            pedagogical_goal="Offer optional reflection without redirecting a valid solution path.",
            student_action="Briefly explain why your answer matches the question.",
            rationale="The work appears acceptable, so any intervention should stay optional and non-corrective.",
            confidence=min(diagnosis.confidence, 0.94),
            notes=["deterministic_pedagogy_state"],
        )

    return PedagogyState(
        intervention_posture=InterventionPosture.CORRECTIVE,
        primary_objective=PedagogicalObjective.CLARIFY_STATE,
        disclosure_policy=DisclosurePolicy.LOW,
        step_grounding_requirement=StepGroundingRequirement.OPTIONAL
        if target_step_id is not None
        else StepGroundingRequirement.NONE,
        candidate_target_step_id=target_step_id,
        candidate_focus_step_ids=[target_step_id] if target_step_id else [],
        focus_semantics=[f"review what the question is asking for: {_target_prompt(problem)}"],
        uncertain_pedagogical_concerns=concerns,
        pedagogical_goal="Clarify the student's current state before giving a stronger corrective hint.",
        student_action="Explain what quantity you are trying to find and why your current result should match it.",
        rationale="The diagnosis suggests intervention is needed, but the verified mechanism is still uncertain.",
        confidence=min(diagnosis.confidence, 0.94),
        notes=["deterministic_pedagogy_state"],
    )


def _disclosure_budget(policy: DisclosurePolicy) -> int:
    return {
        DisclosurePolicy.NONE: 0,
        DisclosurePolicy.LOW: 1,
        DisclosurePolicy.MEDIUM: 2,
    }[policy]


def _project_pedagogy_to_hint_strategy(
    diagnosis_state: DiagnosisState,
    pedagogy_state: PedagogyState,
) -> HintStrategy:
    budget = _disclosure_budget(pedagogy_state.disclosure_policy)
    target_step_id = (
        pedagogy_state.candidate_target_step_id
        if pedagogy_state.step_grounding_requirement != StepGroundingRequirement.NONE
        else None
    )
    focus_points = [] if budget == 0 else _dedupe(list(pedagogy_state.focus_semantics))

    teacher_move = TeacherMove.METACOGNITIVE_PROMPT
    hint_level = HintLevel.CONCEPTUAL

    if pedagogy_state.intervention_posture in {InterventionPosture.NONE, InterventionPosture.ACKNOWLEDGE_CORRECT}:
        teacher_move = TeacherMove.RESTATE_RESULT
        hint_level = HintLevel.CONCEPTUAL
        budget = 0
        target_step_id = None
        focus_points = []
    elif pedagogy_state.primary_objective == PedagogicalObjective.CLARIFY_ANSWER_FORMAT:
        teacher_move = TeacherMove.METACOGNITIVE_PROMPT
        hint_level = HintLevel.CONCEPTUAL
    elif pedagogy_state.primary_objective == PedagogicalObjective.REFOCUS_TARGET:
        teacher_move = TeacherMove.REFOCUS_TARGET
        hint_level = HintLevel.CONCEPTUAL
    elif pedagogy_state.primary_objective == PedagogicalObjective.REPAIR_QUANTITY_RELATIONSHIP:
        teacher_move = TeacherMove.CHECK_RELATIONSHIP
        hint_level = HintLevel.RELATIONAL
    elif pedagogy_state.primary_objective == PedagogicalObjective.RECOMPUTE_ARITHMETIC:
        teacher_move = (
            TeacherMove.RECOMPUTE_STEP
            if diagnosis_state.candidate_localization == ErrorLocalization.INTERMEDIATE_STEP
            else TeacherMove.CONTINUE_FROM_STEP
        )
        hint_level = HintLevel.NEXT_STEP
    elif pedagogy_state.primary_objective == PedagogicalObjective.REINFORCE_UNDERSTANDING:
        teacher_move = (
            TeacherMove.METACOGNITIVE_PROMPT
            if pedagogy_state.intervention_posture == InterventionPosture.REFLECTIVE_OPTIONAL
            else TeacherMove.RESTATE_RESULT
        )
        hint_level = HintLevel.CONCEPTUAL
    elif pedagogy_state.primary_objective == PedagogicalObjective.CLARIFY_STATE:
        teacher_move = TeacherMove.METACOGNITIVE_PROMPT
        hint_level = HintLevel.CONCEPTUAL

    strategy_notes = list(pedagogy_state.notes)
    strategy_notes.append("strategy_projected_from_pedagogy_state")
    return HintStrategy(
        teacher_move=teacher_move,
        hint_level=hint_level,
        pedagogical_goal=pedagogy_state.pedagogical_goal,
        student_action=pedagogy_state.student_action,
        target_step_id=target_step_id,
        disclosure_budget=budget,
        focus_points=focus_points,
        must_not_reveal=[],
        rationale=pedagogy_state.rationale,
        confidence=min(max(pedagogy_state.confidence, 0.2), 0.98),
        notes=strategy_notes,
    )


def _project_strategy_to_plan(
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    strategy: HintStrategy,
) -> HintPlan:
    target_step_id = strategy.target_step_id
    must_not_reveal = _dedupe(
        _base_must_not_reveal(reference)
        + _step_specific_must_not_reveal(reference, target_step_id)
        + list(strategy.must_not_reveal)
    )
    return HintPlan(
        diagnosis_label=diagnosis.diagnosis_label,
        hint_level=strategy.hint_level,
        teacher_move=strategy.teacher_move,
        target_step_id=target_step_id,
        disclosure_budget=strategy.disclosure_budget,
        focus_points=_dedupe(strategy.focus_points),
        must_not_reveal=must_not_reveal,
        rationale=strategy.rationale,
        confidence=min(max(strategy.confidence, 0.2), 0.98),
    )


def build_pedagogy_state(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
    llm_client: LLMClient | None = None,
) -> PedagogyState:
    """Build the internal pedagogical state before projecting to hint actions."""

    if llm_client is not None:
        try:
            pedagogy_state = _llm_build_pedagogy_state(problem, reference, diagnosis, diagnosis_state, llm_client)
            notes = list(pedagogy_state.notes)
            notes.append("llm_pedagogy_state_used")
            return pedagogy_state.model_copy(update={"notes": notes})
        except (LLMGenerationError, ValidationError, ValueError, TypeError, KeyError) as exc:
            pedagogy_state = _deterministic_pedagogy_state(problem, reference, diagnosis, diagnosis_state)
            notes = list(pedagogy_state.notes)
            notes.append("llm_pedagogy_state_failed_fallback")
            notes.append(f"llm_pedagogy_state_failure_reason:{exc}")
            notes.append(str(exc))
            return pedagogy_state.model_copy(update={"notes": notes})

    return _deterministic_pedagogy_state(problem, reference, diagnosis, diagnosis_state)


def build_pedagogy_artifacts(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
    llm_client: LLMClient | None = None,
) -> tuple[PedagogyState, HintStrategy, HintPlan]:
    """Build PedagogyState first, then project it into HintStrategy and HintPlan."""

    pedagogy_state = build_pedagogy_state(
        problem,
        reference,
        diagnosis,
        diagnosis_state,
        llm_client=llm_client,
    )
    strategy = _project_pedagogy_to_hint_strategy(diagnosis_state, pedagogy_state)
    plan = _project_strategy_to_plan(reference, diagnosis, strategy)
    return pedagogy_state, strategy, plan


def build_hint_strategy(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState,
    llm_client: LLMClient | None = None,
) -> tuple[HintStrategy, HintPlan]:
    """Backward-compatible wrapper returning projected HintStrategy and HintPlan."""

    _, strategy, plan = build_pedagogy_artifacts(
        problem,
        reference,
        diagnosis,
        diagnosis_state,
        llm_client=llm_client,
    )
    return strategy, plan


def build_hint_plan(
    problem: FormalizedProblem,
    reference: CanonicalReference,
    diagnosis: DiagnosisResult,
    diagnosis_state: DiagnosisState | None = None,
    llm_client: LLMClient | None = None,
) -> HintPlan:
    """Backward-compatible wrapper that returns only the public hint plan."""

    active_state = diagnosis_state if diagnosis_state is not None else _coarse_state_from_result(diagnosis)
    _, _, plan = build_pedagogy_artifacts(
        problem,
        reference,
        diagnosis,
        active_state,
        llm_client=llm_client,
    )
    return plan
