"""Artifact-first full-pipeline debugger."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from debug_formalizer import (
    RecordingLLMClient,
    _last_successful_record,
    _prepare_commitment_payload as _prepare_problem_commitment_payload,
    _prepare_semantic_payload as _prepare_problem_semantic_payload,
    _task_records,
    _write_json,
    _write_text,
)
from src.diagnosis import build_diagnosis
from src.diagnosis.scoring import build_diagnosis_hypotheses
from src.evidence import build_diagnosis_context, build_diagnosis_evidence
from src.formalizer import formalize_problem, formalize_student_work
from src.formalizer.problem_formalizer_builder import (
    _build_formalized_problem_from_skeleton,
    _heuristic_formalize_problem,
    _merge_semantic_and_commitment_payloads,
)
from src.formalizer.student_work_builder import (
    _build_compact_student_context,
    _build_compact_student_draft,
    _build_student_work_from_artifacts,
    _heuristic_formalize_student_work,
)
from src.formalizer.student_work_validation import _student_sanity_validation_result
from src.hint import generate_hint_text, repair_hint_text, verify_hint_text
from src.hint.controller import _fallback_hint
from src.llm import build_default_llm_client
from src.models import HintMode, HintResult
from src.pedagogy import build_pedagogy_artifacts
from src.runtime import build_canonical_reference, compile_executable_plan, execute_plan, validate_problem_graph


def _build_run_dir(output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_root / f"run_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _stage_dir(run_dir: Path, name: str) -> Path:
    stage_dir = run_dir / name
    stage_dir.mkdir(parents=True, exist_ok=False)
    return stage_dir


def _task_records_many(records: list[dict[str, Any]], task_names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("task_name") in task_names]


def _prepare_student_payload(records: list[dict[str, Any]], task_name: str, note_prefix: str) -> dict[str, Any] | None:
    record, attempt_index = _last_successful_record(records, task_name)
    if record is None:
        return None
    payload = dict(record["response"])
    notes = list(payload.get("notes", []))
    notes.append(f"{note_prefix}:{attempt_index}")
    payload["notes"] = notes
    return payload


def _attempt_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for record in records:
        task_name = str(record.get("task_name", "unknown"))
        task_summary = summary.setdefault(task_name, {"attempt_count": 0, "success_count": 0, "error_count": 0})
        task_summary["attempt_count"] += 1
        if record.get("status") == "success":
            task_summary["success_count"] += 1
        else:
            task_summary["error_count"] += 1
    return summary


def _note_value(notes: list[str], prefix: str) -> str | None:
    for note in notes:
        if note.startswith(prefix):
            return note.split(":", 1)[1]
    return None


def _student_source_summary(student_work) -> dict[str, Any]:
    notes = list(student_work.notes)
    used_llm_student_path = any(
        note in {
            "llm_student_parse_used",
            "llm_student_semantic_state_used",
            "llm_student_trace_commitment_used",
        }
        for note in notes
    )
    fell_back_to_heuristic = any(
        note in {
            "llm_student_parse_failed_fallback",
            "llm_student_semantic_state_failed_fallback",
            "llm_student_trace_commitment_failed_fallback",
            "llm_student_post_build_failed",
        }
        for note in notes
    )
    final_source = "llm" if used_llm_student_path and not fell_back_to_heuristic else "heuristic"
    return {
        "heuristic_source": "heuristic",
        "final_source": final_source,
        "used_llm_student_path": used_llm_student_path,
        "fell_back_to_heuristic": fell_back_to_heuristic,
    }


def _build_hint_result_with_artifacts(
    *,
    problem,
    reference,
    diagnosis,
    hint_strategy,
    hint_plan,
    hint_mode: HintMode,
    llm_client,
) -> tuple[HintResult, str, list[str], dict[str, Any] | None, list[str] | None, str | None, list[str] | None]:
    initial_hint_text = generate_hint_text(
        problem,
        reference,
        hint_plan,
        strategy=hint_strategy,
        hint_mode=hint_mode,
        llm_client=llm_client,
    )
    initial_violations = verify_hint_text(initial_hint_text, hint_plan)
    verification_passed = len(initial_violations) == 0
    final_hint_text = initial_hint_text
    final_violations = list(initial_violations)
    notes: list[str] = []
    repair_payload: dict[str, Any] | None = None
    repaired_violations: list[str] | None = None
    fallback_hint_text: str | None = None
    fallback_violations: list[str] | None = None

    if not verification_passed:
        repair_result = repair_hint_text(
            problem,
            reference,
            diagnosis,
            hint_plan,
            original_hint=initial_hint_text,
            hint_mode=hint_mode,
            llm_client=llm_client,
        )
        repair_payload = {"hint_text": repair_result.hint_text, "notes": list(repair_result.notes)}
        repaired_violations = verify_hint_text(repair_result.hint_text, hint_plan)
        if not repaired_violations:
            final_hint_text = repair_result.hint_text
            final_violations = []
            verification_passed = True
            notes.extend(repair_result.notes)
            notes.append("used_repaired_hint")
        else:
            notes.extend(repair_result.notes)
            fallback_hint_text = _fallback_hint(hint_plan)
            fallback_violations = verify_hint_text(fallback_hint_text, hint_plan)
            if not fallback_violations:
                final_hint_text = fallback_hint_text
                final_violations = []
                verification_passed = True
                notes.append("used_fallback_hint")
            else:
                final_hint_text = repair_result.hint_text
                final_violations = repaired_violations
                notes.append("fallback_hint_still_failed_verification")

    confidence = min(hint_plan.confidence + (0.04 if verification_passed else -0.1), 0.97)
    confidence = max(confidence, 0.2)
    hint_result = HintResult(
        hint_text=final_hint_text,
        hint_level=hint_plan.hint_level,
        hint_mode=hint_mode,
        verification_passed=verification_passed,
        violated_rules=final_violations,
        confidence=confidence,
        notes=notes,
    )
    return (
        hint_result,
        initial_hint_text,
        initial_violations,
        repair_payload,
        repaired_violations,
        fallback_hint_text,
        fallback_violations,
    )


def run_debug_pipeline(
    *,
    problem_text: str,
    student_answer: str,
    hint_mode: HintMode = HintMode.NORMAL,
    use_llm: bool = True,
    output_root: Path | None = None,
) -> Path:
    output_root = output_root or Path("debug_pipeline_artifacts")
    run_dir = _build_run_dir(output_root)

    base_llm_client = build_default_llm_client() if use_llm else None
    recording_llm_client = RecordingLLMClient(base_llm_client) if base_llm_client is not None else None
    active_llm_client = recording_llm_client if recording_llm_client is not None else None

    problem_dir = _stage_dir(run_dir, "01_problem_formalizer")
    reference_dir = _stage_dir(run_dir, "02_reference_builder")
    student_dir = _stage_dir(run_dir, "03_student_work_formalizer")
    evidence_dir = _stage_dir(run_dir, "04_evidence_builder")
    diagnosis_dir = _stage_dir(run_dir, "05_diagnosis")
    hint_plan_dir = _stage_dir(run_dir, "06_hint_plan")
    hint_result_dir = _stage_dir(run_dir, "07_hint_result")

    heuristic_problem, heuristic_evidence = _heuristic_formalize_problem(problem_text)
    problem = formalize_problem(problem_text, llm_client=active_llm_client) if active_llm_client is not None else heuristic_problem

    problem_semantic_payload = (
        _prepare_problem_semantic_payload(recording_llm_client.records, problem_text)
        if recording_llm_client is not None
        else None
    )
    problem_commitment_payload = (
        _prepare_problem_commitment_payload(recording_llm_client.records, problem_text)
        if recording_llm_client is not None
        else None
    )
    typed_problem_draft_error: str | None = None
    if problem_semantic_payload is not None and problem_commitment_payload is not None:
        try:
            merged_problem_payload = _merge_semantic_and_commitment_payloads(
                problem_semantic_payload,
                problem_commitment_payload,
            )
            typed_problem_draft = _build_formalized_problem_from_skeleton(
                problem_text,
                heuristic_problem,
                merged_problem_payload,
            )
        except Exception as exc:
            merged_problem_payload = _merge_semantic_and_commitment_payloads(
                problem_semantic_payload,
                problem_commitment_payload,
            )
            typed_problem_draft = {"available": False, "error": str(exc)}
            typed_problem_draft_error = str(exc)
    else:
        merged_problem_payload = None
        typed_problem_draft = {"available": False, "error": "semantic payload or commitment payload missing"}
        typed_problem_draft_error = "semantic payload or commitment payload missing"

    graph_validation = validate_problem_graph(problem)
    plan = compile_executable_plan(problem)
    trace = execute_plan(plan, problem) if plan.steps else None
    reference_error: str | None = None
    try:
        reference = build_canonical_reference(problem)
    except Exception as exc:
        reference = None
        reference_error = str(exc)

    _write_json(
        problem_dir / "00_run_meta.json",
        {
            "heuristic_provenance": heuristic_problem.provenance.value,
            "final_provenance": problem.provenance.value,
            "graph_valid": graph_validation.is_valid,
            "graph_issue_codes": [issue.code for issue in graph_validation.issues],
            "plan_step_count": len(plan.steps),
            "execution_success": trace.success if trace is not None else False,
            "reference_available": reference is not None,
            "reference_error": reference_error,
            "typed_problem_draft_error": typed_problem_draft_error,
        },
    )
    _write_text(problem_dir / "01_problem_text.txt", problem_text.strip() + "\n")
    _write_json(problem_dir / "02_heuristic_evidence_pack.json", heuristic_evidence)
    _write_json(problem_dir / "03_problem_semantic_state.json", problem_semantic_payload or {"available": False})
    _write_json(problem_dir / "04_plan_commitment.json", problem_commitment_payload or {"available": False})
    _write_json(problem_dir / "05_typed_problem_draft_plus_problem_graph.json", typed_problem_draft)
    _write_json(problem_dir / "06_formalized_problem.json", problem)
    _write_json(problem_dir / "07_executable_plan.json", plan)
    _write_json(problem_dir / "08_execution_trace.json", trace if trace is not None else {"available": False})
    _write_json(problem_dir / "09_canonical_reference.json", reference if reference is not None else {"available": False, "error": reference_error})
    _write_json(problem_dir / "10_graph_validation.json", graph_validation)
    _write_json(problem_dir / "11_merged_llm_payload.json", merged_problem_payload or {"available": False})
    _write_json(
        problem_dir / "12_llm_attempts.json",
        _task_records_many(
            recording_llm_client.records if recording_llm_client is not None else [],
            ("problem_formalizer_semantic_state", "problem_formalizer_executable_commitment"),
        ),
    )

    if reference is None:
        raise RuntimeError(f"Canonical reference unavailable: {reference_error or 'unknown error'}")

    _write_json(reference_dir / "00_run_meta.json", {"plan_step_count": len(plan.steps), "trace_success": trace.success if trace is not None else False, "final_answer": reference.final_answer})
    _write_json(reference_dir / "01_formalized_problem_input.json", problem)
    _write_json(reference_dir / "02_executable_plan.json", plan)
    _write_json(reference_dir / "03_execution_trace.json", trace if trace is not None else {"available": False})
    _write_json(reference_dir / "04_canonical_reference.json", reference)

    heuristic_student = _heuristic_formalize_student_work(student_answer, problem=problem, reference=reference)
    student_work = (
        formalize_student_work(
            student_answer,
            problem=problem,
            reference=reference,
            llm_client=active_llm_client,
        )
        if active_llm_client is not None
        else heuristic_student
    )
    compact_student_context = _build_compact_student_context(problem)
    compact_student_draft = _build_compact_student_draft(heuristic_student, problem=problem)
    student_semantic_payload = (
        _prepare_student_payload(
            recording_llm_client.records,
            "student_work_semantic_state",
            "llm_student_semantic_state_attempt",
        )
        if recording_llm_client is not None
        else None
    )
    student_commitment_payload = (
        _prepare_student_payload(
            recording_llm_client.records,
            "student_work_trace_commitment",
            "llm_student_trace_commitment_attempt",
        )
        if recording_llm_client is not None
        else None
    )
    typed_student_draft_error: str | None = None
    if student_semantic_payload is not None and student_commitment_payload is not None:
        try:
            typed_student_draft = _build_student_work_from_artifacts(
                student_answer,
                heuristic_student,
                student_semantic_payload,
                student_commitment_payload,
                problem=problem,
            )
        except Exception as exc:
            typed_student_draft = {"available": False, "error": str(exc)}
            typed_student_draft_error = str(exc)
    else:
        typed_student_draft = {"available": False, "error": "semantic payload or commitment payload missing"}
        typed_student_draft_error = "semantic payload or commitment payload missing"
    student_validation = _student_sanity_validation_result(student_work, problem)
    student_source_summary = _student_source_summary(student_work)

    _write_json(
        student_dir / "00_run_meta.json",
        {
            **student_source_summary,
            "heuristic_mode": heuristic_student.mode.value,
            "final_mode": student_work.mode.value,
            "normalized_final_answer": student_work.normalized_final_answer,
            "selected_target_ref": student_work.selected_target_ref,
            "student_graph_present": student_work.student_graph is not None,
            "sanity_valid": student_validation.is_valid,
            "sanity_issue_codes": [issue.code for issue in student_validation.issues],
            "typed_student_draft_error": typed_student_draft_error,
        },
    )
    _write_text(student_dir / "01_student_answer.txt", student_answer.strip() + "\n")
    _write_json(student_dir / "02_problem_context.json", compact_student_context)
    _write_json(student_dir / "03_heuristic_student_work.json", heuristic_student)
    _write_json(student_dir / "04_compact_heuristic_draft.json", compact_student_draft)
    _write_json(student_dir / "05_student_semantic_state.json", student_semantic_payload or {"available": False})
    _write_json(student_dir / "06_student_trace_commitment.json", student_commitment_payload or {"available": False})
    _write_json(student_dir / "07_typed_student_draft_plus_graph.json", typed_student_draft)
    _write_json(student_dir / "08_student_work_state.json", student_work)
    _write_json(student_dir / "09_student_sanity_validation.json", student_validation)
    _write_json(
        student_dir / "10_llm_attempts.json",
        _task_records_many(
            recording_llm_client.records if recording_llm_client is not None else [],
            ("student_work_semantic_state", "student_work_trace_commitment"),
        ),
    )

    evidence = build_diagnosis_evidence(problem, reference, student_work)
    diagnosis_context = build_diagnosis_context(problem, reference, student_work, evidence)
    _write_json(
        evidence_dir / "00_run_meta.json",
        {
            "evidence_item_count": len(evidence.evidence_items),
            "alignment_item_count": len(evidence.alignment_map),
            "first_divergence_step_id": evidence.first_divergence_step_id,
            "confidence": evidence.confidence,
            "context_problem_quantity_count": len(diagnosis_context.problem_quantities),
            "context_reference_step_count": len(diagnosis_context.reference_steps),
            "context_student_step_count": len(diagnosis_context.student_steps),
        },
    )
    _write_json(evidence_dir / "01_problem_snapshot.json", problem)
    _write_json(evidence_dir / "02_reference_snapshot.json", reference)
    _write_json(evidence_dir / "03_student_snapshot.json", student_work)
    _write_json(evidence_dir / "04_diagnosis_evidence.json", evidence)
    _write_json(evidence_dir / "05_diagnosis_context.json", diagnosis_context)

    hypotheses = build_diagnosis_hypotheses(evidence)
    deterministic_diagnosis_state, deterministic_diagnosis = build_diagnosis(
        evidence,
        context=diagnosis_context,
        llm_client=None,
    )
    diagnosis_state, diagnosis = build_diagnosis(
        evidence,
        context=diagnosis_context,
        llm_client=active_llm_client,
    )
    leaderboard = [
        {
            "diagnosis_label": hypothesis.label.value,
            "subtype": hypothesis.subtype,
            "localization": hypothesis.localization.value,
            "score": hypothesis.score,
            "summary": hypothesis.summary,
            "rationale": hypothesis.rationale,
            "supporting_evidence_types": hypothesis.supporting_evidence_types,
        }
        for hypothesis in hypotheses
    ]
    _write_json(
        diagnosis_dir / "00_run_meta.json",
        {
            "hypothesis_count": len(hypotheses),
            "context_problem_quantity_count": len(diagnosis_context.problem_quantities),
            "context_reference_step_count": len(diagnosis_context.reference_steps),
            "context_student_step_count": len(diagnosis_context.student_steps),
            "used_llm_diagnosis": "llm_first_diagnosis_used" in diagnosis.notes,
            "fell_back_to_deterministic": "llm_diagnosis_failed_fallback" in diagnosis.notes,
            "llm_diagnosis_failure_stage": _note_value(diagnosis.notes, "llm_diagnosis_failure_stage:"),
            "llm_diagnosis_failure_reason": _note_value(diagnosis.notes, "llm_diagnosis_failure_reason:"),
            "answer_acceptability": diagnosis_state.answer_acceptability.value,
            "target_alignment": diagnosis_state.target_alignment.value,
            "process_equivalence": diagnosis_state.process_equivalence.value,
            "intervention_required": diagnosis_state.intervention_required,
            "verified_error_mechanisms": diagnosis_state.verified_error_mechanisms,
            "uncertain_concerns": diagnosis_state.uncertain_concerns,
            "final_label": diagnosis.diagnosis_label.value,
            "target_step_id": diagnosis.target_step_id,
            "confidence": diagnosis.confidence,
        },
    )
    _write_json(diagnosis_dir / "01_evidence_input.json", evidence)
    _write_json(diagnosis_dir / "02_context_input.json", diagnosis_context)
    _write_json(diagnosis_dir / "03_hypothesis_leaderboard.json", leaderboard)
    _write_json(diagnosis_dir / "04_deterministic_diagnosis_state.json", deterministic_diagnosis_state)
    _write_json(diagnosis_dir / "05_deterministic_diagnosis.json", deterministic_diagnosis)
    _write_json(diagnosis_dir / "06_final_diagnosis_state.json", diagnosis_state)
    _write_json(diagnosis_dir / "07_final_diagnosis.json", diagnosis)
    _write_json(
        diagnosis_dir / "08_llm_attempts.json",
        [
            record
            for record in (recording_llm_client.records if recording_llm_client is not None else [])
            if str(record.get("task_name", "")).startswith("diagnosis")
        ],
    )

    pedagogy_state, hint_strategy, hint_plan = build_pedagogy_artifacts(
        problem,
        reference,
        diagnosis,
        diagnosis_state,
        llm_client=active_llm_client,
    )
    _write_json(
        hint_plan_dir / "00_run_meta.json",
        {
            "pedagogy_intervention_posture": pedagogy_state.intervention_posture.value,
            "pedagogy_primary_objective": pedagogy_state.primary_objective.value,
            "strategy_teacher_move": hint_strategy.teacher_move.value,
            "teacher_move": hint_plan.teacher_move.value,
            "hint_level": hint_plan.hint_level.value,
            "target_step_id": hint_plan.target_step_id,
            "confidence": hint_plan.confidence,
        },
    )
    _write_json(hint_plan_dir / "01_problem_snapshot.json", problem)
    _write_json(hint_plan_dir / "02_reference_snapshot.json", reference)
    _write_json(hint_plan_dir / "03_diagnosis_state_input.json", diagnosis_state)
    _write_json(hint_plan_dir / "04_diagnosis_input.json", diagnosis)
    _write_json(hint_plan_dir / "05_pedagogy_state.json", pedagogy_state)
    _write_json(hint_plan_dir / "06_hint_strategy.json", hint_strategy)
    _write_json(hint_plan_dir / "07_hint_plan.json", hint_plan)

    (
        hint_result,
        initial_hint_text,
        initial_violations,
        repair_payload,
        repaired_violations,
        fallback_hint_text,
        fallback_violations,
    ) = _build_hint_result_with_artifacts(
        problem=problem,
        reference=reference,
        diagnosis=diagnosis,
        hint_strategy=hint_strategy,
        hint_plan=hint_plan,
        hint_mode=hint_mode,
        llm_client=active_llm_client,
    )
    _write_json(
        hint_result_dir / "00_run_meta.json",
        {
            "verification_passed": hint_result.verification_passed,
            "hint_mode": hint_result.hint_mode.value,
            "hint_level": hint_result.hint_level.value,
            "confidence": hint_result.confidence,
            "used_repaired_hint": "used_repaired_hint" in hint_result.notes,
            "used_fallback_hint": "used_fallback_hint" in hint_result.notes,
        },
    )
    _write_json(hint_result_dir / "01_problem_snapshot.json", problem)
    _write_json(hint_result_dir / "02_reference_snapshot.json", reference)
    _write_json(hint_result_dir / "03_diagnosis_state_input.json", diagnosis_state)
    _write_json(hint_result_dir / "04_diagnosis_input.json", diagnosis)
    _write_json(hint_result_dir / "05_pedagogy_state_input.json", pedagogy_state)
    _write_json(hint_result_dir / "06_hint_strategy_input.json", hint_strategy)
    _write_json(hint_result_dir / "07_hint_plan_input.json", hint_plan)
    _write_json(hint_result_dir / "08_initial_hint_text.json", {"hint_text": initial_hint_text})
    _write_json(hint_result_dir / "09_initial_verification.json", {"verification_passed": len(initial_violations) == 0, "violated_rules": initial_violations})
    _write_json(hint_result_dir / "10_repair_result.json", {"available": repair_payload is not None, "repair_result": repair_payload, "violated_rules": repaired_violations})
    _write_json(hint_result_dir / "11_fallback_hint.json", {"available": fallback_hint_text is not None, "hint_text": fallback_hint_text, "violated_rules": fallback_violations})
    _write_json(hint_result_dir / "12_final_hint_result.json", hint_result)
    _write_json(
        hint_result_dir / "13_llm_attempts.json",
        _task_records_many(
            recording_llm_client.records if recording_llm_client is not None else [],
            ("pedagogy_state", "hint_generator", "hint_repair"),
        ),
    )

    _write_json(
        run_dir / "00_run_meta.json",
        {
            "llm_requested": use_llm,
            "llm_available": base_llm_client is not None,
            "hint_mode": hint_mode.value,
            "problem_provenance": problem.provenance.value,
            **student_source_summary,
            "student_mode": student_work.mode.value,
            "student_final_answer": student_work.normalized_final_answer,
            "diagnosis_label": diagnosis.diagnosis_label.value,
            "diagnosis_answer_acceptability": diagnosis_state.answer_acceptability.value,
            "diagnosis_target_alignment": diagnosis_state.target_alignment.value,
            "diagnosis_intervention_required": diagnosis_state.intervention_required,
            "diagnosis_used_llm_first": "llm_first_diagnosis_used" in diagnosis.notes,
            "diagnosis_fell_back_to_deterministic": "llm_diagnosis_failed_fallback" in diagnosis.notes,
            "diagnosis_fallback_stage": _note_value(diagnosis.notes, "llm_diagnosis_failure_stage:"),
            "diagnosis_fallback_reason": _note_value(diagnosis.notes, "llm_diagnosis_failure_reason:"),
            "pedagogy_intervention_posture": pedagogy_state.intervention_posture.value,
            "pedagogy_primary_objective": pedagogy_state.primary_objective.value,
            "pedagogy_used_llm": "llm_pedagogy_state_used" in pedagogy_state.notes,
            "pedagogy_fell_back_to_deterministic": "llm_pedagogy_state_failed_fallback" in pedagogy_state.notes,
            "pedagogy_fallback_reason": _note_value(pedagogy_state.notes, "llm_pedagogy_state_failure_reason:"),
            "hint_teacher_move": hint_strategy.teacher_move.value,
            "hint_verified": hint_result.verification_passed,
            "attempt_summary": _attempt_summary(recording_llm_client.records if recording_llm_client is not None else []),
        },
    )
    _write_json(
        run_dir / "08_final_pipeline_result.json",
        {
            "problem": problem,
            "reference": reference,
            "student_work": student_work,
            "evidence": evidence,
            "diagnosis_context": diagnosis_context,
            "diagnosis_state": diagnosis_state,
            "diagnosis": diagnosis,
            "pedagogy_state": pedagogy_state,
            "hint_strategy": hint_strategy,
            "hint_plan": hint_plan,
            "hint_result": hint_result,
        },
    )
    _write_text(
        run_dir / "README.txt",
        "\n".join(
            [
                "Full Tutoring Pipeline Artifact Export",
                f"Artifact directory: {run_dir}",
                f"Problem provenance: {problem.provenance.value}",
                f"Student final source: {student_source_summary['final_source']}",
                f"Student mode: {student_work.mode.value}",
                f"Student normalized answer: {student_work.normalized_final_answer}",
                f"Diagnosis label: {diagnosis.diagnosis_label.value}",
                f"Hint verified: {hint_result.verification_passed}",
            ]
        )
        + "\n",
    )

    return run_dir
