"""Validation and feedback helpers for student-work formalization."""
from __future__ import annotations

import re

from src.models import (
    FormalizedProblem,
    GraphValidationIssue,
    GraphValidationResult,
    ProblemGraphEdgeType,
    ProblemGraphNodeType,
    StudentWorkMode,
    StudentWorkState,
    TraceOperation,
)


_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")
_FRACTION_PATTERN = re.compile(r"(?<!\d)(-?\d+)\s*/\s*(\d+)(?!\d)")
_PERCENT_PATTERN = re.compile(r"(-?\d[\d,]*\.?\d*)\s*%")
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
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_GROUNDING_STOPWORDS = {
    "a",
    "an",
    "and",
    "answer",
    "be",
    "because",
    "equation",
    "final",
    "first",
    "from",
    "i",
    "in",
    "is",
    "it",
    "last",
    "line",
    "of",
    "or",
    "second",
    "so",
    "states",
    "student",
    "students",
    "that",
    "the",
    "their",
    "then",
    "third",
    "to",
    "uses",
    "with",
}


def _payload_issue(
    code: str,
    message: str,
    *,
    step_id: str | None = None,
    node_id: str | None = None,
    details: dict | None = None,
) -> GraphValidationIssue:
    return GraphValidationIssue(
        code=code,
        message=message,
        step_id=step_id,
        node_id=node_id,
        details=details or {},
    )


def _normalize_text_anchor(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _numeric_literals_in_text(text: str) -> list[float]:
    values: list[float] = []
    for match in _NUMBER_PATTERN.findall(text or ""):
        normalized = match.replace(",", "")
        if normalized.endswith("."):
            normalized = normalized[:-1]
        try:
            values.append(float(normalized))
        except ValueError:
            continue
    for numerator_text, denominator_text in _FRACTION_PATTERN.findall(text or ""):
        try:
            numerator = float(numerator_text)
            denominator = float(denominator_text)
        except ValueError:
            continue
        if abs(denominator) <= 1e-12:
            continue
        values.append(numerator / denominator)
    for percent_text in _PERCENT_PATTERN.findall(text or ""):
        normalized = percent_text.replace(",", "")
        if normalized.endswith("."):
            normalized = normalized[:-1]
        try:
            values.append(float(normalized) / 100.0)
        except ValueError:
            continue
    return values


def _is_close_number(left: float | None, right: float | None, tolerance: float = 1e-9) -> bool:
    return left is not None and right is not None and abs(left - right) <= tolerance


def _string_is_grounded_in_answer(text: str | None, raw_answer: str) -> bool:
    normalized_text = _normalize_text_anchor(text or "")
    normalized_answer = _normalize_text_anchor(raw_answer)
    if not normalized_text or not normalized_answer:
        return False
    if normalized_text in normalized_answer:
        return True

    for span in _split_answer_spans(raw_answer):
        normalized_span = _normalize_text_anchor(span)
        if not normalized_span:
            continue
        if normalized_span in normalized_text or normalized_text in normalized_span:
            return True

    grounding_numbers = _numeric_literals_in_text(text or "")
    answer_numbers = _numeric_literals_in_text(raw_answer)
    if grounding_numbers and not all(
        any(_is_close_number(value, observed) for observed in answer_numbers)
        for value in grounding_numbers
    ):
        return False

    grounding_tokens = {
        token.lower()
        for token in _TOKEN_PATTERN.findall(text or "")
        if token and token.lower() not in _GROUNDING_STOPWORDS and len(token) > 1
    }
    answer_tokens = {
        token.lower()
        for token in _TOKEN_PATTERN.findall(raw_answer)
        if token and token.lower() not in _GROUNDING_STOPWORDS and len(token) > 1
    }
    return len(grounding_tokens.intersection(answer_tokens)) >= 2


def _value_is_grounded_in_answer(value: float | int | None, raw_answer: str) -> bool:
    if value is None or not isinstance(value, (int, float)):
        return False
    return any(_is_close_number(observed, float(value)) for observed in _numeric_literals_in_text(raw_answer))


def _allowed_problem_ref_ids(problem: FormalizedProblem | None) -> set[str]:
    refs: set[str] = set()
    if problem is not None:
        refs.update(quantity.quantity_id for quantity in _visible_problem_quantities(problem))
        if problem.target is not None:
            if problem.target.target_quantity_id is not None:
                refs.add(problem.target.target_quantity_id)
            refs.add(problem.target.target_variable)
    return refs


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

    if _quantity_provenance_value(quantity) == "problem_text":
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


def _split_answer_spans(raw_answer: str) -> list[str]:
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


def _is_answer_only_span(span: str) -> bool:
    stripped = (span or "").strip()
    if not stripped:
        return False
    return bool(
        _ANSWER_PATTERN.search(stripped)
        or _GET_ANSWER_PATTERN.search(stripped)
        or _SINGLE_NUMBER_ANSWER_PATTERN.fullmatch(stripped)
    )


def _span_looks_like_trace(span: str) -> bool:
    stripped = (span or "").strip()
    if not stripped or _is_answer_only_span(stripped):
        return False
    if "=" in stripped:
        return True
    if any(symbol in stripped for symbol in ("+", "-", "*", "/", "%")):
        return True
    return len(_numeric_literals_in_text(stripped)) >= 2


def _visible_trace_spans(raw_answer: str) -> list[str]:
    return [span for span in _split_answer_spans(raw_answer) if _span_looks_like_trace(span)]


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


def validate_llm_student_semantic_state_payload(
    payload: dict,
    *,
    allowed_refs: set[str],
    raw_answer: str,
    problem: FormalizedProblem | None,
) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    notes: list[str] = []

    forbidden_keys = {"trace_steps", "assumptions"}
    forbidden_present = sorted(key for key in forbidden_keys if key in payload)
    if forbidden_present:
        issues.append(
            _payload_issue(
                "student_semantic_state_contains_commitment_fields",
                "Semantic-state payload must not contain trace-step commitment fields.",
                details={"forbidden_keys": forbidden_present},
            )
        )

    mode_value = payload.get("mode")
    try:
        mode = StudentWorkMode(mode_value)
    except ValueError:
        mode = None
        issues.append(
            _payload_issue(
                "student_invalid_mode",
                "mode must use a valid StudentWorkMode enum value.",
                details={"mode": mode_value},
            )
        )

    final_answer_block = payload.get("final_answer")
    if not isinstance(final_answer_block, dict):
        issues.append(_payload_issue("student_missing_final_answer_block", "final_answer must be an object."))
    else:
        final_value = final_answer_block.get("value")
        if final_value is not None and not isinstance(final_value, (int, float)):
            issues.append(
                _payload_issue(
                    "student_invalid_final_answer_value",
                    "final_answer.value must be numeric or null.",
                    details={"value": final_value},
                )
            )
        elif final_value is not None and not _value_is_grounded_in_answer(final_value, raw_answer):
            issues.append(
                _payload_issue(
                    "student_ungrounded_final_answer_value",
                    "final_answer.value must be grounded in the student answer text.",
                    details={"value": final_value},
                )
            )

    target_block = payload.get("target")
    if not isinstance(target_block, dict):
        issues.append(_payload_issue("student_missing_target_block", "target must be an object."))
    else:
        selected_ref = target_block.get("selected_ref")
        if selected_ref is not None:
            if not isinstance(selected_ref, str) or not selected_ref.strip():
                issues.append(
                    _payload_issue(
                        "student_invalid_selected_target_ref",
                        "target.selected_ref must be null or a non-empty string.",
                    )
                )
            elif selected_ref not in allowed_refs:
                issues.append(
                    _payload_issue(
                        "student_invalid_selected_target_ref",
                        "target.selected_ref must reference a known problem ref.",
                        details={"selected_target_ref": selected_ref},
                    )
                )

    semantic_facts = payload.get("semantic_facts")
    if semantic_facts is None:
        semantic_facts = []
    if not isinstance(semantic_facts, list):
        issues.append(_payload_issue("student_invalid_semantic_facts", "semantic_facts must be a list."))
    else:
        seen_fact_ids: set[str] = set()
        for index, fact in enumerate(semantic_facts, start=1):
            if not isinstance(fact, dict):
                issues.append(
                    _payload_issue(
                        "student_invalid_semantic_fact",
                        "semantic_facts must contain objects only.",
                        details={"index": index},
                    )
                )
                continue

            fact_id = str(fact.get("fact_id", "")).strip()
            if not fact_id:
                issues.append(_payload_issue("student_missing_fact_id", "Each semantic_fact must include fact_id."))
                continue
            if fact_id in seen_fact_ids:
                issues.append(
                    _payload_issue(
                        "student_duplicate_fact_id",
                        "semantic_facts contains duplicate fact_id values.",
                        node_id=fact_id,
                    )
                )
            seen_fact_ids.add(fact_id)

            label = str(fact.get("label", "")).strip()
            if not label:
                issues.append(
                    _payload_issue(
                        "student_missing_fact_label",
                        "Each semantic_fact must include a non-empty label.",
                        node_id=fact_id,
                    )
                )

            value = fact.get("value")
            if value is not None and not isinstance(value, (int, float)):
                issues.append(
                    _payload_issue(
                        "student_invalid_fact_value",
                        "semantic_fact.value must be numeric or null.",
                        node_id=fact_id,
                        details={"value": value},
                    )
                )
            grounding = fact.get("grounding")
            if not isinstance(grounding, str) or not grounding.strip():
                issues.append(
                    _payload_issue(
                        "student_missing_fact_grounding",
                        "Each semantic_fact must include non-empty grounding copied from the student answer.",
                        node_id=fact_id,
                    )
                )
            elif not _string_is_grounded_in_answer(grounding, raw_answer):
                issues.append(
                    _payload_issue(
                        "student_ungrounded_fact_grounding",
                        "semantic_fact.grounding must be traceable to the student answer, ideally by quoting or closely reusing a supporting phrase or line.",
                        node_id=fact_id,
                        details={"grounding": grounding},
                    )
                )

    if mode == StudentWorkMode.FINAL_ANSWER_ONLY and isinstance(final_answer_block, dict):
        if final_answer_block.get("value") is None:
            issues.append(
                _payload_issue(
                    "student_missing_final_answer",
                    "final_answer_only mode requires a grounded final_answer.value.",
                )
            )
    if mode == StudentWorkMode.UNPARSEABLE and isinstance(final_answer_block, dict):
        if final_answer_block.get("value") is not None:
            issues.append(
                _payload_issue(
                    "student_unparseable_with_final_answer",
                    "unparseable mode must not include a final_answer.value.",
                )
            )

    if mode == StudentWorkMode.FINAL_ANSWER_ONLY and target_block is not None:
        notes.append("student_mode_final_answer_only")
    if mode == StudentWorkMode.UNPARSEABLE:
        notes.append("student_mode_unparseable")

    return GraphValidationResult(
        is_valid=not issues,
        issues=issues,
        operation_node_count=0,
        notes=notes or ["student_semantic_state_validation"],
    )


def validate_llm_student_trace_commitment_payload(
    payload: dict,
    *,
    raw_answer: str,
    semantic_payload: dict,
    allowed_refs: set[str],
    problem_ref_values: dict[str, float],
) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    notes: list[str] = []

    forbidden_keys = {"final_answer", "mode", "target", "semantic_facts"}
    forbidden_present = sorted(key for key in forbidden_keys if key in payload)
    if forbidden_present:
        issues.append(
            _payload_issue(
                "student_trace_commitment_redefines_semantics",
                "Trace commitment payload must not redefine semantic-state fields.",
                details={"forbidden_keys": forbidden_present},
            )
        )

    semantic_mode = StudentWorkMode(semantic_payload.get("mode", StudentWorkMode.UNPARSEABLE.value))
    semantic_final_answer = None
    final_answer_block = semantic_payload.get("final_answer")
    if isinstance(final_answer_block, dict) and isinstance(final_answer_block.get("value"), (int, float)):
        semantic_final_answer = float(final_answer_block.get("value"))
    selected_target_ref = None
    target_block = semantic_payload.get("target")
    if isinstance(target_block, dict):
        selected_ref = target_block.get("selected_ref")
        if isinstance(selected_ref, str) and selected_ref.strip():
            selected_target_ref = selected_ref.strip()
    semantic_fact_ids = {
        str(fact.get("fact_id", "")).strip()
        for fact in semantic_payload.get("semantic_facts", [])
        if isinstance(fact, dict) and str(fact.get("fact_id", "")).strip()
    }
    semantic_fact_values = {
        str(fact.get("fact_id", "")).strip(): float(fact.get("value"))
        for fact in semantic_payload.get("semantic_facts", [])
        if isinstance(fact, dict)
        and str(fact.get("fact_id", "")).strip()
        and isinstance(fact.get("value"), (int, float))
    }
    allowed_step_refs = set(allowed_refs).union(semantic_fact_ids)

    trace_steps = payload.get("trace_steps")
    if trace_steps is None:
        trace_steps = []
    if not isinstance(trace_steps, list):
        issues.append(_payload_issue("student_invalid_trace_steps", "trace_steps must be a list."))
        trace_steps = []

    if semantic_mode in {StudentWorkMode.FINAL_ANSWER_ONLY, StudentWorkMode.UNPARSEABLE} and trace_steps:
        issues.append(
            _payload_issue(
                "student_unexpected_trace_steps",
                "trace_steps must be empty when semantic mode is final_answer_only or unparseable.",
            )
        )
    if semantic_mode in {StudentWorkMode.PARTIAL_TRACE, StudentWorkMode.FULL_TRACE} and not trace_steps:
        issues.append(
            _payload_issue(
                "student_missing_trace_steps",
                "trace_steps must be provided when semantic mode is partial_trace or full_trace.",
            )
        )

    normalized_answer = _normalize_text_anchor(raw_answer)
    matching_final_answer_output = False
    for index, step in enumerate(trace_steps, start=1):
        step_id = f"trace_step_{index}"
        if not isinstance(step, dict):
            issues.append(
                _payload_issue(
                    "student_invalid_trace_step",
                    "trace_steps must contain objects only.",
                    step_id=step_id,
                )
            )
            continue

        surface_text = str(step.get("surface_text", "")).strip()
        if not surface_text:
            issues.append(
                _payload_issue(
                    "student_missing_step_surface_text",
                    "Each trace step must include surface_text.",
                    step_id=step_id,
                )
            )
        elif _normalize_text_anchor(surface_text) not in normalized_answer:
            issues.append(
                _payload_issue(
                    "student_ungrounded_step_surface_text",
                    "trace_steps.surface_text must be grounded in the student answer.",
                    step_id=step_id,
                    details={"surface_text": surface_text},
                )
            )

        operation = step.get("operation")
        if operation is None:
            issues.append(
                _payload_issue(
                    "student_missing_step_operation",
                    "Each trace step must include an operation.",
                    step_id=step_id,
                )
            )
        else:
            try:
                TraceOperation(operation)
            except ValueError:
                issues.append(
                    _payload_issue(
                        "student_invalid_step_operation",
                        "trace_steps.operation must use a valid TraceOperation enum value.",
                        step_id=step_id,
                        details={"operation": operation},
                    )
                )

        referenced_ids = step.get("referenced_ids", [])
        if referenced_ids is None:
            referenced_ids = []
        if not isinstance(referenced_ids, list):
            issues.append(
                _payload_issue(
                    "student_invalid_referenced_ids",
                    "trace_steps.referenced_ids must be a list.",
                    step_id=step_id,
                )
            )
            referenced_ids = []

        unknown_refs = [
            ref_id
            for ref_id in referenced_ids
            if not isinstance(ref_id, str) or not ref_id.strip() or ref_id not in allowed_step_refs
        ]
        if unknown_refs:
            issues.append(
                _payload_issue(
                    "student_unknown_referenced_ids",
                    "trace_steps.referenced_ids must use only known problem refs or semantic fact ids.",
                    step_id=step_id,
                    details={"unknown_refs": unknown_refs},
                )
            )

        literal_numbers = _numeric_literals_in_text(surface_text)
        value_groundings = dict(problem_ref_values)
        value_groundings.update(semantic_fact_values)

        extracted_value = step.get("extracted_value")
        if extracted_value is not None:
            if not isinstance(extracted_value, (int, float)):
                issues.append(
                    _payload_issue(
                        "student_invalid_extracted_value",
                        "trace_steps.extracted_value must be numeric or null.",
                        step_id=step_id,
                        details={"value": extracted_value},
                    )
                )
            else:
                extracted_float = float(extracted_value)
                grounded = any(_is_close_number(observed, extracted_float) for observed in literal_numbers)
                if not grounded:
                    grounded = any(
                        _is_close_number(value_groundings.get(ref_id), extracted_float)
                        for ref_id in referenced_ids
                        if isinstance(ref_id, str)
                    )
                if not grounded:
                    issues.append(
                        _payload_issue(
                            "student_ungrounded_extracted_value",
                            "trace_steps.extracted_value must be supported by the step text or referenced ids.",
                            step_id=step_id,
                            details={"value": extracted_float},
                        )
                    )
                elif semantic_final_answer is not None and _is_close_number(extracted_float, semantic_final_answer):
                    matching_final_answer_output = True

        input_values = step.get("input_values", [])
        if input_values is None:
            input_values = []
        if not isinstance(input_values, list):
            issues.append(
                _payload_issue(
                    "student_invalid_input_values",
                    "trace_steps.input_values must be a list.",
                    step_id=step_id,
                )
            )
            input_values = []
        for input_value in input_values:
            if not isinstance(input_value, (int, float)):
                issues.append(
                    _payload_issue(
                        "student_invalid_input_value",
                        "Each input_values item must be numeric.",
                        step_id=step_id,
                        details={"value": input_value},
                    )
                )
                continue
            input_float = float(input_value)
            grounded = any(_is_close_number(observed, input_float) for observed in literal_numbers)
            if not grounded:
                grounded = any(
                    _is_close_number(value_groundings.get(ref_id), input_float)
                    for ref_id in referenced_ids
                    if isinstance(ref_id, str)
                )

    if (
        semantic_mode in {StudentWorkMode.PARTIAL_TRACE, StudentWorkMode.FULL_TRACE}
        and semantic_final_answer is not None
        and selected_target_ref is None
        and not matching_final_answer_output
    ):
        issues.append(
            _payload_issue(
                "student_missing_final_answer_trace_support",
                "When final_answer.value is present and target.selected_ref is null, at least one visible trace step must carry extracted_value equal to the final answer.",
                details={"final_answer": semantic_final_answer},
            )
        )

    return GraphValidationResult(
        is_valid=not issues,
        issues=issues,
        operation_node_count=len(trace_steps),
        notes=notes or ["student_trace_commitment_validation"],
    )


def _student_sanity_validation_result(
    student_state: StudentWorkState,
    problem: FormalizedProblem | None,
) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    allowed_problem_refs = _allowed_problem_ref_ids(problem)

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
    elif student_state.student_graph is not None:
        graph = student_state.student_graph
        nodes_by_id = {node.node_id: node for node in graph.nodes}
        edges = list(graph.edges)

        if graph.target_node_id is None:
            issues.append(
                GraphValidationIssue(
                    code="student_graph_missing_target",
                    message="student_graph must define target_node_id when present",
                )
            )
        elif graph.target_node_id not in nodes_by_id:
            issues.append(
                GraphValidationIssue(
                    code="student_graph_target_node_missing",
                    message="student_graph.target_node_id must refer to a graph node",
                    node_id=graph.target_node_id,
                )
            )

        for step in student_state.steps:
            op_node_id = f"student_op_{step.step_id}"
            op_node = nodes_by_id.get(op_node_id)
            if op_node is None or op_node.node_type != ProblemGraphNodeType.OPERATION:
                issues.append(
                    GraphValidationIssue(
                        code="student_graph_missing_operation_node",
                        message="student_graph is missing an operation node for a structured step",
                        step_id=step.step_id,
                        node_id=op_node_id,
                    )
                )
                continue

            for ref_id in step.referenced_ids:
                has_input_edge = any(
                    edge.edge_type == ProblemGraphEdgeType.INPUT_TO_OPERATION
                    and edge.source_node_id == ref_id
                    and edge.target_node_id == op_node_id
                    for edge in edges
                )
                if not has_input_edge:
                    issues.append(
                        GraphValidationIssue(
                            code="student_graph_missing_input_edge",
                            message="student_graph is missing an input edge for a referenced ref",
                            step_id=step.step_id,
                            node_id=op_node_id,
                            details={"ref_id": ref_id},
                        )
                    )

            if step.extracted_value is not None:
                has_output_edge = any(
                    edge.edge_type == ProblemGraphEdgeType.OUTPUT_FROM_OPERATION
                    and edge.source_node_id == op_node_id
                    for edge in edges
                )
                if not has_output_edge:
                    issues.append(
                        GraphValidationIssue(
                            code="student_graph_missing_output_edge",
                            message="student_graph is missing an output edge for a step with extracted_value",
                            step_id=step.step_id,
                            node_id=op_node_id,
                        )
                    )

        if student_state.normalized_final_answer is not None and graph.target_node_id is not None:
            incoming_target_edges = [
                edge
                for edge in edges
                if edge.edge_type == ProblemGraphEdgeType.TARGETS_VALUE and edge.target_node_id == graph.target_node_id
            ]
            if not incoming_target_edges and (student_state.steps or student_state.selected_target_ref is not None):
                issues.append(
                    GraphValidationIssue(
                        code="student_graph_missing_target_link",
                        message="student_graph target node should be linked from a selected ref or matching step output",
                        node_id=graph.target_node_id,
                    )
                )

            if student_state.selected_target_ref is not None:
                has_selected_ref_edge = any(
                    edge.edge_type == ProblemGraphEdgeType.TARGETS_VALUE
                    and edge.target_node_id == graph.target_node_id
                    and edge.source_node_id == student_state.selected_target_ref
                    for edge in edges
                )
                if not has_selected_ref_edge:
                    issues.append(
                        GraphValidationIssue(
                            code="student_graph_missing_selected_target_link",
                            message="student_graph target node is missing the selected_target_ref edge",
                            node_id=graph.target_node_id,
                            details={"selected_target_ref": student_state.selected_target_ref},
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
