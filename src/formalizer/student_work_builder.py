"""Deterministic draft building and semantic-sketch compilation for student work."""
from __future__ import annotations

import re

from pydantic import ValidationError

from src.formalizer.reference_trace import build_student_partial_trace, parse_trace_step
from src.formalizer.student_work_graph import build_student_work_graph
from src.models import (
    CanonicalReference,
    FormalizedProblem,
    GraphValidationIssue,
    GraphValidationResult,
    ProvenanceSource,
    StudentSemanticFact,
    StudentStepAttempt,
    StudentWorkMode,
    StudentWorkState,
    TraceOperation,
)


_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")
_FRACTION_PATTERN = re.compile(r"(?<!\d)(-?\d+)\s*/\s*(\d+)(?!\d)")
_PERCENT_PATTERN = re.compile(r"(-?\d[\d,]*\.?\d*)\s*%")
_HASH_PATTERN = re.compile(r"####\s*(-?\d[\d,]*\.?\d*)")
_ANSWER_PATTERN = re.compile(
    r"(?:answer|final answer)\s*(?:is|=|:)?\s*(-?\d[\d,]*\.?\d*)",
    re.IGNORECASE,
)
_GET_ANSWER_PATTERN = re.compile(
    r"(?:so\s+)?i\s+(?:get|got)\s*(-?\d[\d,]*\.?\d*)",
    re.IGNORECASE,
)
_SINGLE_NUMBER_ANSWER_PATTERN = re.compile(r"^\s*(-?\d[\d,]*\.?\d*)\s*\.?\s*$")
_STEP_SPLIT_PATTERN = re.compile(r"(?:\r?\n)+")


def _coerce_list_of_strings(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    return [str(value).strip()] if str(value).strip() else []


def _parse_number(text: str) -> float | None:
    normalized = text.strip().replace(",", "")
    if normalized.endswith(".") and normalized[:-1].replace("-", "", 1).replace(".", "", 1).isdigit():
        normalized = normalized[:-1]
    try:
        return float(normalized)
    except ValueError:
        return None


def _extract_final_answer(raw_answer: str) -> tuple[float | None, list[str]]:
    notes: list[str] = []
    if not raw_answer.strip():
        return None, ["empty_answer"]

    hash_match = _HASH_PATTERN.search(raw_answer)
    if hash_match:
        parsed = _parse_number(hash_match.group(1))
        if parsed is not None:
            return parsed, ["hash_marker_match"]
        notes.append("hash_marker_unparseable")

    answer_match = _ANSWER_PATTERN.search(raw_answer)
    if answer_match:
        parsed = _parse_number(answer_match.group(1))
        if parsed is not None:
            return parsed, ["answer_cue_match"]
        notes.append("answer_cue_unparseable")

    get_match = _GET_ANSWER_PATTERN.search(raw_answer)
    if get_match:
        parsed = _parse_number(get_match.group(1))
        if parsed is not None:
            return parsed, ["get_answer_cue_match"]
        notes.append("get_answer_cue_unparseable")

    single_number_match = _SINGLE_NUMBER_ANSWER_PATTERN.fullmatch(raw_answer.strip())
    if single_number_match:
        parsed = _parse_number(single_number_match.group(1))
        if parsed is not None:
            return parsed, ["single_numeric_answer"]
        notes.append("single_numeric_answer_unparseable")

    notes.append("no_explicit_final_answer")
    return None, notes


def _split_student_steps(raw_answer: str) -> list[str]:
    if not raw_answer.strip():
        return []

    raw_lines = [segment.strip() for segment in _STEP_SPLIT_PATTERN.split(raw_answer) if segment.strip()]
    if len(raw_lines) > 1:
        return raw_lines

    sentence_lines = [
        segment.strip()
        for segment in re.split(r"(?<=[.!?])(?:\s+|(?=[A-Z0-9]))", raw_answer)
        if segment.strip()
    ]
    if len(sentence_lines) > 1:
        return sentence_lines

    return [raw_answer.strip()]


def _normalize_text_anchor(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _is_close_number(left: float | None, right: float | None, tolerance: float = 1e-9) -> bool:
    return left is not None and right is not None and abs(left - right) <= tolerance


def _observed_numbers_in_text(text: str) -> list[float]:
    numbers: list[float] = []
    for match in _NUMBER_PATTERN.findall(text or ""):
        parsed = _parse_number(match)
        if parsed is not None:
            numbers.append(parsed)
    for numerator_text, denominator_text in _FRACTION_PATTERN.findall(text or ""):
        numerator = _parse_number(numerator_text)
        denominator = _parse_number(denominator_text)
        if numerator is None or denominator in {None, 0.0}:
            continue
        numbers.append(float(numerator) / float(denominator))
    for percent_text in _PERCENT_PATTERN.findall(text or ""):
        parsed = _parse_number(percent_text)
        if parsed is None:
            continue
        numbers.append(float(parsed) / 100.0)
    return numbers


def _known_problem_ref_values(problem: FormalizedProblem | None) -> dict[str, float]:
    if problem is None:
        return {}
    return {quantity.quantity_id: quantity.value for quantity in _visible_problem_quantities(problem)}


def _quantity_provenance_value(quantity: object) -> str | None:
    provenance = getattr(quantity, "provenance", None)
    if provenance is None:
        return None
    if hasattr(provenance, "value"):
        return str(provenance.value)
    return str(provenance)


def _is_visible_problem_quantity(quantity: object, problem: FormalizedProblem | None) -> bool:
    if quantity is None:
        return False
    char_start = getattr(quantity, "char_start", None)
    char_end = getattr(quantity, "char_end", None)
    if char_start is not None and char_end is not None:
        return True

    provenance_value = _quantity_provenance_value(quantity)
    if provenance_value == ProvenanceSource.PROBLEM_TEXT.value:
        return True

    for note in getattr(quantity, "notes", []) or []:
        if isinstance(note, str) and note.startswith("semantic_state_origin:observed"):
            return True

    problem_text = problem.problem_text if problem is not None else ""
    surface_text = getattr(quantity, "surface_text", None)
    if isinstance(surface_text, str):
        normalized_surface = _normalize_text_anchor(surface_text)
        normalized_problem = _normalize_text_anchor(problem_text)
        if normalized_surface and normalized_problem and normalized_surface in normalized_problem:
            return True

    return False


def _visible_problem_quantities(problem: FormalizedProblem | None) -> list:
    if problem is None:
        return []
    return [quantity for quantity in problem.quantities if _is_visible_problem_quantity(quantity, problem)]


def _step_visibly_commits_numeric_result(step: StudentStepAttempt) -> bool:
    raw_text = step.raw_text or ""
    if "=" in raw_text:
        return True
    if _ANSWER_PATTERN.search(raw_text) or _GET_ANSWER_PATTERN.search(raw_text):
        return True
    return _SINGLE_NUMBER_ANSWER_PATTERN.fullmatch(raw_text.strip()) is not None


def _derive_visible_final_answer_from_steps(
    steps: list[StudentStepAttempt],
) -> tuple[float | None, list[str]]:
    for step in reversed(steps):
        if step.extracted_value is not None and _step_visibly_commits_numeric_result(step):
            return step.extracted_value, ["final_answer_from_last_visible_step"]
    return None, []


def _step_confidence(operation: TraceOperation | None, extracted_value: float | None, raw_text: str) -> float:
    if operation is not None and operation != TraceOperation.UNKNOWN and extracted_value is not None:
        return 0.82
    if extracted_value is not None and "=" in raw_text:
        return 0.72
    if extracted_value is not None:
        return 0.58
    return 0.25


def _referenced_problem_quantity_ids(line: str, problem: FormalizedProblem | None) -> list[str]:
    if problem is None:
        return []

    lowered_line = line.lower()
    referenced_ids: list[str] = []
    seen: set[str] = set()
    for quantity in _visible_problem_quantities(problem):
        mentions_value = quantity.surface_text.lower() in lowered_line or f"{quantity.value:g}" in lowered_line
        if mentions_value and quantity.quantity_id not in seen:
            referenced_ids.append(quantity.quantity_id)
            seen.add(quantity.quantity_id)
    return referenced_ids


def _build_step_attempts(
    raw_answer: str,
    problem: FormalizedProblem | None,
) -> tuple[list[StudentStepAttempt], list[str]]:
    lines = _split_student_steps(raw_answer)
    trace = build_student_partial_trace(raw_answer)
    notes = list(trace.notes)
    if len(lines) > 1:
        notes.append(f"student_span_candidates={len(lines)}")
    attempts: list[StudentStepAttempt] = []

    for index, line in enumerate(lines, start=1):
        parsed_line = parse_trace_step(line, index, trace.final_value)
        extracted_value = parsed_line.output_value
        operation = parsed_line.operation
        input_values = list(parsed_line.input_values)
        referenced_ids = _referenced_problem_quantity_ids(line, problem)

        step_notes: list[str] = []
        if parsed_line.provenance != ProvenanceSource.UNKNOWN:
            step_notes.append(f"trace_provenance={parsed_line.provenance.value}")
        if "=" in line:
            step_notes.append("contains_equation")
        if referenced_ids:
            step_notes.append(f"referenced_ids={len(referenced_ids)}")
        number_matches = _NUMBER_PATTERN.findall(line)
        if number_matches:
            step_notes.append(f"observed_numbers={len(number_matches)}")

        attempts.append(
            StudentStepAttempt(
                step_id=f"student_step_{index}",
                raw_text=line,
                operation=operation,
                input_values=input_values,
                extracted_value=extracted_value,
                referenced_ids=referenced_ids,
                confidence=_step_confidence(operation, extracted_value, line),
                notes=step_notes,
            )
        )

    return attempts, notes


def _infer_mode(raw_answer: str, steps: list[StudentStepAttempt], final_answer: float | None) -> StudentWorkMode:
    if not raw_answer.strip() or final_answer is None and not steps:
        return StudentWorkMode.UNPARSEABLE
    if len(steps) >= 2 or any("=" in step.raw_text for step in steps):
        return StudentWorkMode.PARTIAL_TRACE
    if len(steps) == 1 and "=" in steps[0].raw_text and final_answer is not None:
        return StudentWorkMode.PARTIAL_TRACE
    return StudentWorkMode.FINAL_ANSWER_ONLY if final_answer is not None else StudentWorkMode.UNPARSEABLE


def _infer_selected_target_ref(
    final_answer: float | None,
    problem: FormalizedProblem | None,
) -> str | None:
    return None


def _attach_student_graph(
    student_state: StudentWorkState,
    problem: FormalizedProblem | None,
    *,
    provenance_override: ProvenanceSource | None = None,
) -> StudentWorkState:
    student_graph = build_student_work_graph(
        student_state,
        problem=problem,
        provenance_override=provenance_override,
    )
    if student_graph is None:
        return student_state
    return student_state.model_copy(update={"student_graph": student_graph})


def _heuristic_formalize_student_work(
    raw_answer: str,
    problem: FormalizedProblem | None = None,
    reference: CanonicalReference | None = None,
) -> StudentWorkState:
    cleaned_answer = (raw_answer or "").strip()
    final_answer, final_answer_notes = _extract_final_answer(cleaned_answer)
    steps, trace_notes = _build_step_attempts(cleaned_answer, problem)
    if final_answer is None:
        derived_final_answer, derivation_notes = _derive_visible_final_answer_from_steps(steps)
        if derived_final_answer is not None:
            final_answer = derived_final_answer
            final_answer_notes.extend(derivation_notes)
    mode = _infer_mode(cleaned_answer, steps, final_answer)
    selected_target_ref = _infer_selected_target_ref(final_answer, problem)

    notes = list(final_answer_notes)
    notes.extend(trace_notes)
    if selected_target_ref is not None:
        notes.append(f"selected_target_ref={selected_target_ref}")
    if mode == StudentWorkMode.UNPARSEABLE:
        notes.append("student_work_unparseable")

    confidence = 0.0
    if final_answer is not None:
        confidence += 0.35
    if steps:
        confidence += min(0.4, 0.1 * len(steps))
    if selected_target_ref is not None:
        confidence += 0.15
    if mode == StudentWorkMode.PARTIAL_TRACE:
        confidence += 0.05

    return _attach_student_graph(
        StudentWorkState(
            raw_answer=cleaned_answer,
            normalized_final_answer=final_answer,
            mode=mode,
            semantic_facts=[],
            steps=steps if mode != StudentWorkMode.FINAL_ANSWER_ONLY else [],
            student_graph=None,
            selected_target_ref=selected_target_ref,
            assumptions=[],
            confidence=min(confidence, 0.95),
            notes=notes,
        ),
        problem=problem,
    )


def _reconcile_student_mode(
    requested_mode: StudentWorkMode,
    *,
    steps: list[StudentStepAttempt],
    normalized_final_answer: float | None,
) -> tuple[StudentWorkMode, list[str]]:
    inferred_mode = _infer_mode("", steps, normalized_final_answer)
    notes: list[str] = []
    if requested_mode in {StudentWorkMode.FINAL_ANSWER_ONLY, StudentWorkMode.UNPARSEABLE} and steps:
        repaired_mode = StudentWorkMode.FULL_TRACE if len(steps) >= 2 else StudentWorkMode.PARTIAL_TRACE
        notes.append(f"local_mode_repair:{requested_mode.value}->{repaired_mode.value}")
        return repaired_mode, notes
    if requested_mode in {StudentWorkMode.PARTIAL_TRACE, StudentWorkMode.FULL_TRACE} and not steps:
        if normalized_final_answer is not None:
            notes.append(f"local_mode_repair:{requested_mode.value}->final_answer_only")
            return StudentWorkMode.FINAL_ANSWER_ONLY, notes
        notes.append(f"local_mode_repair:{requested_mode.value}->unparseable")
        return StudentWorkMode.UNPARSEABLE, notes
    if requested_mode == StudentWorkMode.UNPARSEABLE and normalized_final_answer is not None:
        repaired_mode = inferred_mode if inferred_mode != StudentWorkMode.UNPARSEABLE else StudentWorkMode.FINAL_ANSWER_ONLY
        notes.append(f"local_mode_repair:unparseable->{repaired_mode.value}")
        return repaired_mode, notes
    return requested_mode, notes


def _build_compact_student_draft(
    heuristic_state: StudentWorkState,
    problem: FormalizedProblem | None = None,
) -> dict:
    candidate_spans = _split_student_steps(heuristic_state.raw_answer)
    return {
        "observed_final_answer": heuristic_state.normalized_final_answer,
        "candidate_step_count": len(candidate_spans),
        "candidate_step_hints": [
            {
                "span_index": index,
                "observed_numbers": [
                    _parse_number(match)
                    for match in _NUMBER_PATTERN.findall(span)
                    if _parse_number(match) is not None
                ],
                "referenced_ids": _referenced_problem_quantity_ids(span, problem),
                "contains_equation": "=" in span,
            }
            for index, span in enumerate(candidate_spans, start=1)
        ],
        "allowed_problem_refs": _allowed_student_refs(problem),
        "heuristic_notes": list(heuristic_state.notes),
    }


def _canonical_student_ref_payloads(
    problem: FormalizedProblem | None,
) -> list[dict]:
    refs: list[dict] = []
    seen_ref_ids: set[str] = set()

    if problem is not None:
        for quantity in _visible_problem_quantities(problem):
            if quantity.quantity_id in seen_ref_ids:
                continue
            seen_ref_ids.add(quantity.quantity_id)
            refs.append(
                {
                    "ref_id": quantity.quantity_id,
                    "kind": "problem_quantity",
                    "label": quantity.surface_text,
                    "value": quantity.value,
                    "unit": quantity.unit,
                    "semantic_role": quantity.semantic_role.value,
                }
            )

        if (
            problem.target is not None
            and problem.target.target_quantity_id is not None
            and problem.target.target_quantity_id not in seen_ref_ids
        ):
            target_quantity = next(
                (quantity for quantity in problem.quantities if quantity.quantity_id == problem.target.target_quantity_id),
                None,
            )
            seen_ref_ids.add(problem.target.target_quantity_id)
            refs.append(
                {
                    "ref_id": problem.target.target_quantity_id,
                    "kind": "problem_target_quantity",
                    "label": (
                        target_quantity.surface_text
                        if target_quantity is not None and target_quantity.surface_text
                        else problem.target.description or problem.target.surface_text
                    ),
                    "value": (
                        target_quantity.value
                        if target_quantity is not None and _is_visible_problem_quantity(target_quantity, problem)
                        else None
                    ),
                    "unit": (
                        target_quantity.unit
                        if target_quantity is not None and target_quantity.unit is not None
                        else problem.target.unit
                    ),
                    "semantic_role": (
                        target_quantity.semantic_role.value
                        if target_quantity is not None
                        else None
                    ),
                }
            )

        if problem.target is not None and problem.target.target_variable not in seen_ref_ids:
            seen_ref_ids.add(problem.target.target_variable)
            refs.append(
                {
                    "ref_id": problem.target.target_variable,
                    "kind": "problem_target",
                    "label": problem.target.description or problem.target.surface_text,
                    "value": None,
                    "unit": problem.target.unit,
                }
            )

    return refs


def _build_compact_student_context(
    problem: FormalizedProblem | None,
) -> dict:
    return {
        "problem_text": problem.problem_text if problem is not None else None,
        "problem_target": (
            {
                "target_variable": problem.target.target_variable,
                "target_quantity_id": problem.target.target_quantity_id,
                "surface_text": problem.target.surface_text,
                "description": problem.target.description,
                "unit": problem.target.unit,
            }
            if problem is not None and problem.target is not None
            else None
        ),
        "problem_refs": _canonical_student_ref_payloads(problem),
    }


def _build_student_target_from_sketch(
    heuristic_state: StudentWorkState,
    sketch: dict,
) -> str | None:
    target_block = sketch.get("target")
    if not isinstance(target_block, dict):
        return heuristic_state.selected_target_ref
    selected_ref = target_block.get("selected_ref")
    return str(selected_ref).strip() if isinstance(selected_ref, str) and str(selected_ref).strip() else None


def _build_student_semantic_facts_from_sketch(sketch: dict) -> list[StudentSemanticFact]:
    fact_blocks = sketch.get("semantic_facts", [])
    if fact_blocks is None:
        return []
    if not isinstance(fact_blocks, list):
        raise ValueError("semantic_facts must be a list when provided")

    semantic_facts: list[StudentSemanticFact] = []
    for index, fact in enumerate(fact_blocks, start=1):
        if not isinstance(fact, dict):
            raise ValueError("semantic_facts must contain objects only")
        fact_payload = {
            "fact_id": fact.get("fact_id") or f"student_fact_{index}",
            "label": fact.get("label") or fact.get("surface_text"),
            "value": fact.get("value"),
            "grounding": fact.get("grounding"),
            "confidence": float(fact.get("confidence", 0.0)),
            "notes": list(fact.get("notes", [])),
        }
        validated_fact = StudentSemanticFact.model_validate(fact_payload)
        if validated_fact.confidence <= 0.0:
            validated_fact = validated_fact.model_copy(
                update={
                    "confidence": 0.55 if validated_fact.grounding else 0.4,
                    "notes": list(validated_fact.notes) + ["local_semantic_fact_repair:recomputed_confidence"],
                }
            )
        semantic_facts.append(validated_fact)
    return semantic_facts


def _is_grounded_numeric_value(
    value: float,
    *,
    surface_text: str,
    referenced_ids: list[str],
    problem_ref_values: dict[str, float],
    semantic_fact_values: dict[str, float],
) -> bool:
    if any(_is_close_number(observed, value) for observed in _observed_numbers_in_text(surface_text)):
        return True

    for ref_id in referenced_ids:
        if ref_id in problem_ref_values and _is_close_number(problem_ref_values[ref_id], value):
            return True
        if ref_id in semantic_fact_values and _is_close_number(semantic_fact_values[ref_id], value):
            return True
    return False


def _sanitize_student_step_payload(
    raw_step: dict,
    *,
    surface_text: str,
    referenced_ids: list[str],
    problem_ref_values: dict[str, float],
    semantic_fact_values: dict[str, float],
    fallback_confidence: float,
) -> tuple[dict, list[str]]:
    notes = list(raw_step.get("notes", []))
    extracted_value = raw_step.get("extracted_value")
    if isinstance(extracted_value, (int, float)):
        extracted_value = float(extracted_value)
    else:
        extracted_value = None if extracted_value is None else extracted_value

    input_values: list[float] = []
    for input_value in raw_step.get("input_values", []):
        if not isinstance(input_value, (int, float)):
            continue
        numeric_value = float(input_value)
        if _is_grounded_numeric_value(
            numeric_value,
            surface_text=surface_text,
            referenced_ids=referenced_ids,
            problem_ref_values=problem_ref_values,
            semantic_fact_values=semantic_fact_values,
        ):
            input_values.append(numeric_value)
        else:
            notes.append(f"local_step_repair:dropped_ungrounded_input_value:{numeric_value:g}")

    confidence = raw_step.get("confidence", fallback_confidence)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = fallback_confidence
    if confidence <= 0.0:
        confidence = _step_confidence(raw_step.get("operation"), extracted_value, surface_text)
        notes.append("local_step_repair:recomputed_step_confidence")

    return {
        "operation": raw_step.get("operation"),
        "input_values": input_values,
        "extracted_value": extracted_value,
        "confidence": confidence,
        "notes": notes,
    }, notes


def _prune_student_semantic_facts(
    semantic_facts: list[StudentSemanticFact],
    steps: list[StudentStepAttempt],
) -> tuple[list[StudentSemanticFact], list[str]]:
    referenced_fact_ids = {
        ref_id
        for step in steps
        for ref_id in step.referenced_ids
        if any(fact.fact_id == ref_id for fact in semantic_facts)
    }
    notes: list[str] = []
    deduped: list[StudentSemanticFact] = []
    seen_signatures: set[tuple[str, float | None, str]] = set()

    for fact in semantic_facts:
        if fact.fact_id not in referenced_fact_ids:
            notes.append(f"local_semantic_fact_pruned:unreferenced:{fact.fact_id}")
            continue
        signature = (_normalize_text_anchor(fact.label), fact.value, _normalize_text_anchor(fact.grounding or ""))
        if signature in seen_signatures:
            notes.append(f"local_semantic_fact_pruned:duplicate:{fact.fact_id}")
            continue
        seen_signatures.add(signature)
        deduped.append(fact)

    return deduped, notes


def _repair_selected_target_ref(
    selected_target_ref: str | None,
    *,
    normalized_final_answer: float | None,
    problem: FormalizedProblem | None,
) -> tuple[str | None, list[str]]:
    if problem is None or problem.target is None:
        return selected_target_ref, []
    if selected_target_ref is None:
        return selected_target_ref, []

    notes: list[str] = []
    canonical_target_ref = problem.target.target_quantity_id or problem.target.target_variable
    if canonical_target_ref and selected_target_ref == canonical_target_ref:
        return selected_target_ref, []

    if (
        canonical_target_ref
        and problem.target.target_quantity_id is not None
        and selected_target_ref == problem.target.target_variable
    ):
        notes.append(
            f"local_target_repair:normalized_target_alias:{selected_target_ref}->{problem.target.target_quantity_id}"
        )
        return problem.target.target_quantity_id, notes

    quantity_by_id = {quantity.quantity_id: quantity for quantity in problem.quantities}
    selected_quantity = quantity_by_id.get(selected_target_ref)
    if (
        selected_quantity is not None
        and normalized_final_answer is not None
        and not _is_close_number(selected_quantity.value, normalized_final_answer)
    ):
        repaired_ref = canonical_target_ref
        if repaired_ref and repaired_ref != selected_target_ref:
            notes.append(
                f"local_target_repair:retargeted_selected_ref:{selected_target_ref}->{repaired_ref}"
            )
            return repaired_ref, notes

    return selected_target_ref, notes


def _resolve_step_surface_text(
    raw_answer: str,
    heuristic_state: StudentWorkState,
    step_payload: dict,
    step_index: int,
) -> str:
    candidate = step_payload.get("surface_text")
    if isinstance(candidate, str) and candidate.strip():
        normalized_candidate = _normalize_text_anchor(candidate)
        normalized_answer = _normalize_text_anchor(raw_answer)
        if normalized_candidate and normalized_candidate in normalized_answer:
            return candidate.strip()
        raise ValueError(f"trace_steps[{step_index}] surface_text is not grounded in the student answer")

    raise ValueError(f"trace_steps[{step_index}] is missing grounded surface_text")


def _build_student_steps_from_sketch(
    raw_answer: str,
    heuristic_state: StudentWorkState,
    sketch: dict,
    *,
    allowed_problem_refs: set[str],
    semantic_fact_ids: set[str],
    problem: FormalizedProblem | None,
    semantic_fact_values: dict[str, float],
) -> list[StudentStepAttempt]:
    requested_mode = StudentWorkMode(sketch.get("mode", heuristic_state.mode))
    trace_steps = sketch.get("trace_steps", [])
    if trace_steps is None:
        trace_steps = []
    if not isinstance(trace_steps, list):
        raise ValueError("trace_steps must be a list when provided")
    if not trace_steps:
        if requested_mode in {StudentWorkMode.FINAL_ANSWER_ONLY, StudentWorkMode.UNPARSEABLE}:
            return []
        raise ValueError("trace_steps must be provided for partial/full trace modes")
    compiled_steps: list[StudentStepAttempt] = []
    problem_ref_values = _known_problem_ref_values(problem)
    for index, raw_step in enumerate(trace_steps, start=1):
        if not isinstance(raw_step, dict):
            raise ValueError("trace_steps must contain objects only")

        referenced_ids = [
            ref_id
            for ref_id in raw_step.get("referenced_ids", [])
            if isinstance(ref_id, str) and ref_id.strip()
        ]
        deduped_refs: list[str] = []
        seen_refs: set[str] = set()
        for ref_id in referenced_ids:
            if ref_id not in seen_refs:
                deduped_refs.append(ref_id)
                seen_refs.add(ref_id)

        surface_text = _resolve_step_surface_text(raw_answer, heuristic_state, raw_step, index - 1)
        sanitized_step_payload, _ = _sanitize_student_step_payload(
            raw_step,
            surface_text=surface_text,
            referenced_ids=deduped_refs,
            problem_ref_values=problem_ref_values,
            semantic_fact_values=semantic_fact_values,
            fallback_confidence=heuristic_state.confidence or 0.0,
        )
        step_payload = {
            "step_id": f"student_step_{index}",
            "raw_text": surface_text,
            "operation": sanitized_step_payload["operation"],
            "input_values": sanitized_step_payload["input_values"],
            "extracted_value": sanitized_step_payload["extracted_value"],
            "referenced_ids": deduped_refs,
            "confidence": sanitized_step_payload["confidence"],
            "notes": sanitized_step_payload["notes"],
        }
        compiled_steps.append(StudentStepAttempt.model_validate(step_payload))

    return compiled_steps


def _merge_student_semantic_and_commitment_payloads(
    semantic_payload: dict,
    commitment_payload: dict,
) -> dict:
    merged = dict(semantic_payload)
    merged.update(commitment_payload)
    merged["notes"] = _coerce_list_of_strings(semantic_payload.get("notes")) + _coerce_list_of_strings(
        commitment_payload.get("notes")
    )
    merged["assumptions"] = _coerce_list_of_strings(commitment_payload.get("assumptions"))
    merged["trace_steps"] = [
        step for step in commitment_payload.get("trace_steps", []) if isinstance(step, dict)
    ]
    merged["confidence"] = commitment_payload.get("confidence", semantic_payload.get("confidence"))
    return merged


def _build_student_work_from_artifacts(
    raw_answer: str,
    heuristic_state: StudentWorkState,
    semantic_payload: dict,
    commitment_payload: dict,
    *,
    problem: FormalizedProblem | None = None,
) -> StudentWorkState:
    merged = _merge_student_semantic_and_commitment_payloads(semantic_payload, commitment_payload)
    allowed_problem_refs = set(_allowed_student_refs(problem))
    requested_mode = StudentWorkMode(semantic_payload.get("mode", heuristic_state.mode))
    local_notes: list[str] = []
    semantic_facts = _build_student_semantic_facts_from_sketch(semantic_payload)
    semantic_fact_ids = {fact.fact_id for fact in semantic_facts}
    semantic_fact_values = {
        fact.fact_id: fact.value for fact in semantic_facts if fact.value is not None
    }
    steps = _build_student_steps_from_sketch(
        raw_answer,
        heuristic_state,
        merged,
        allowed_problem_refs=allowed_problem_refs,
        semantic_fact_ids=semantic_fact_ids,
        problem=problem,
        semantic_fact_values=semantic_fact_values,
    )
    if steps:
        semantic_facts, prune_notes = _prune_student_semantic_facts(semantic_facts, steps)
        local_notes.extend(prune_notes)

    final_answer_block = semantic_payload.get("final_answer")
    normalized_final_answer = None
    if isinstance(final_answer_block, dict) and "value" in final_answer_block:
        normalized_final_answer = final_answer_block.get("value")
    if isinstance(normalized_final_answer, int):
        normalized_final_answer = float(normalized_final_answer)
    if normalized_final_answer is None:
        normalized_final_answer, derivation_notes = _derive_visible_final_answer_from_steps(steps)
        local_notes.extend(derivation_notes)

    overall_confidence = merged.get("confidence", heuristic_state.confidence)
    try:
        overall_confidence = float(overall_confidence)
    except (TypeError, ValueError):
        overall_confidence = heuristic_state.confidence
    if overall_confidence <= 0.0:
        inferred_confidence = heuristic_state.confidence
        if inferred_confidence <= 0.0:
            inferred_confidence = 0.6 if normalized_final_answer is not None else 0.35
        overall_confidence = inferred_confidence

    selected_target_ref = _build_student_target_from_sketch(heuristic_state, semantic_payload)

    merged_payload = heuristic_state.model_dump(mode="json")
    merged_payload.update(
        {
            "raw_answer": (raw_answer or "").strip(),
            "normalized_final_answer": normalized_final_answer,
            "mode": requested_mode,
            "semantic_facts": [fact.model_dump(mode="json") for fact in semantic_facts],
            "steps": [step.model_dump(mode="json") for step in steps],
            "selected_target_ref": selected_target_ref,
            "assumptions": list(merged.get("assumptions", heuristic_state.assumptions)),
            "confidence": overall_confidence,
            "notes": list(heuristic_state.notes) + list(merged.get("notes", [])) + local_notes + ["llm_student_parse_used"],
            "student_graph": None,
        }
    )

    try:
        merged_state = StudentWorkState.model_validate(merged_payload)
    except ValidationError as exc:
        raise exc

    return _attach_student_graph(
        merged_state,
        problem=problem,
        provenance_override=ProvenanceSource.LLM,
    )


def _allowed_student_refs(
    problem: FormalizedProblem | None,
) -> list[str]:
    return sorted(item["ref_id"] for item in _canonical_student_ref_payloads(problem))


def _compare_with_heuristic_student_notes(
    heuristic_state: StudentWorkState,
    refined_state: StudentWorkState,
) -> list[str]:
    notes: list[str] = []
    if heuristic_state.normalized_final_answer != refined_state.normalized_final_answer:
        notes.append("student_llm_diff:normalized_final_answer")
    if heuristic_state.mode != refined_state.mode:
        notes.append("student_llm_diff:mode")
    if heuristic_state.selected_target_ref != refined_state.selected_target_ref:
        notes.append("student_llm_diff:selected_target_ref")
    if len(heuristic_state.steps) != len(refined_state.steps):
        notes.append("student_llm_diff:step_count")
        return notes
    for heuristic_step, refined_step in zip(heuristic_state.steps, refined_state.steps):
        if heuristic_step.operation != refined_step.operation:
            notes.append(f"student_llm_diff:operation:{refined_step.step_id}")
        if heuristic_step.extracted_value != refined_step.extracted_value:
            notes.append(f"student_llm_diff:value:{refined_step.step_id}")
        if heuristic_step.referenced_ids != refined_step.referenced_ids:
            notes.append(f"student_llm_diff:refs:{refined_step.step_id}")
    return notes


def _schema_validation_result(exc: ValidationError | ValueError | TypeError) -> GraphValidationResult:
    if isinstance(exc, ValidationError):
        issues = [
            GraphValidationIssue(
                code="student_schema_validation_error",
                message=error["msg"],
                details={"loc": list(error["loc"])},
            )
            for error in exc.errors()
        ]
    else:
        issues = [GraphValidationIssue(code="student_schema_build_error", message=str(exc))]
    return GraphValidationResult(
        is_valid=False,
        issues=issues,
        operation_node_count=0,
        notes=["student_schema_validation_failed"],
    )
