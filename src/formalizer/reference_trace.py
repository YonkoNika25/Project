"""Shared trace builders for structured reference/student reasoning traces.

This module is intentionally neutral: both legacy symbolic code and the new
formalizer/runtime stack can reuse it without creating reverse dependencies.
"""
from __future__ import annotations

import re

from src.models import (
    ProvenanceSource,
    SymbolicTrace,
    TraceOperation,
    TraceStep,
)


_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")
_BINARY_EQUATION_PATTERN = re.compile(
    r"(-?\d[\d,]*\.?\d*)\s*([+\-*/xX])\s*(-?\d[\d,]*\.?\d*)\s*=\s*(-?\d[\d,]*\.?\d*)"
)
_PERCENT_OF_PATTERN = re.compile(
    r"(-?\d[\d,]*\.?\d*)\s*% of\s*(-?\d[\d,]*\.?\d*)\s*=\s*(-?\d[\d,]*\.?\d*)",
    re.IGNORECASE,
)


def strip_reference_markers(solution_text: str) -> list[str]:
    cleaned_lines: list[str] = []
    for line in (solution_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("####"):
            stripped = stripped.replace("####", "", 1).strip()
        cleaned_lines.append(stripped)
    return cleaned_lines


def parse_trace_step(line: str, step_index: int, final_value: float | None) -> TraceStep:
    # Priority parse: percent-of form, then binary equation, then fallback numeric derive.
    percent_match = _PERCENT_OF_PATTERN.search(line)
    if percent_match:
        rate = float(percent_match.group(1).replace(",", ""))
        base = float(percent_match.group(2).replace(",", ""))
        output = float(percent_match.group(3).replace(",", ""))
        return TraceStep(
            step_index=step_index,
            raw_text=line,
            operation=TraceOperation.PERCENT_OF,
            input_values=[rate, base],
            output_value=output,
            output_label=f"step_{step_index}_output",
            is_final_target=final_value is not None and abs(output - final_value) < 1e-9,
            confidence=0.92,
            provenance=ProvenanceSource.SOLVER_REFERENCE,
        )

    equation_match = _BINARY_EQUATION_PATTERN.search(line)
    if equation_match:
        left = float(equation_match.group(1).replace(",", ""))
        op = equation_match.group(2)
        right = float(equation_match.group(3).replace(",", ""))
        output = float(equation_match.group(4).replace(",", ""))
        operation = {
            "+": TraceOperation.ADD,
            "-": TraceOperation.SUBTRACT,
            "*": TraceOperation.MULTIPLY,
            "/": TraceOperation.DIVIDE,
            "x": TraceOperation.MULTIPLY,
            "X": TraceOperation.MULTIPLY,
        }.get(op, TraceOperation.UNKNOWN)
        return TraceStep(
            step_index=step_index,
            raw_text=line,
            operation=operation,
            input_values=[left, right],
            output_value=output,
            output_label=f"step_{step_index}_output",
            is_final_target=final_value is not None and abs(output - final_value) < 1e-9,
            confidence=0.95,
            provenance=ProvenanceSource.SOLVER_REFERENCE,
        )

    output = None
    matches = _NUMBER_PATTERN.findall(line)
    if matches:
        try:
            output = float(matches[-1].replace(",", ""))
        except ValueError:
            output = None

    return TraceStep(
        step_index=step_index,
        raw_text=line,
        operation=TraceOperation.DERIVE if output is not None else TraceOperation.UNKNOWN,
        input_values=[],
        output_value=output,
        output_label=f"step_{step_index}_output" if output is not None else None,
        is_final_target=final_value is not None and output is not None and abs(output - final_value) < 1e-9,
        confidence=0.45 if output is not None else 0.2,
        provenance=ProvenanceSource.SOLVER_REFERENCE,
    )


def build_reference_trace(reference_solution_text: str, target_text: str = "") -> SymbolicTrace:
    """Build a lightweight symbolic trace from reference solution text."""
    lines = strip_reference_markers(reference_solution_text)
    if not lines:
        return SymbolicTrace(
            steps=[],
            final_value=None,
            target_label=target_text or None,
            confidence=0.0,
            notes=["reference_trace_missing"],
            provenance=ProvenanceSource.UNKNOWN,
        )

    # Seed final value from trailing number in the last line when available.
    final_value = None
    trailing_numbers = _NUMBER_PATTERN.findall(lines[-1])
    if trailing_numbers:
        try:
            final_value = float(trailing_numbers[-1].replace(",", ""))
        except ValueError:
            final_value = None

    steps = [parse_trace_step(line, idx, final_value) for idx, line in enumerate(lines, start=1)]
    if final_value is None:
        for step in reversed(steps):
            if step.output_value is not None:
                final_value = step.output_value
                step.is_final_target = True
                break

    confidence = 0.0
    if steps:
        confidence = sum(step.confidence for step in steps) / len(steps)
    if steps and any(step.operation != TraceOperation.UNKNOWN for step in steps):
        confidence = min(confidence + 0.1, 1.0)

    notes = [f"trace_steps={len(steps)}"]
    if final_value is not None:
        notes.append("trace_final_value_detected")
    if any(step.operation == TraceOperation.UNKNOWN for step in steps):
        notes.append("trace_contains_unknown_steps")

    return SymbolicTrace(
        steps=steps,
        final_value=final_value,
        target_label=target_text or None,
        confidence=max(0.0, min(confidence, 1.0)),
        notes=notes,
        provenance=ProvenanceSource.SOLVER_REFERENCE,
    )


def build_student_partial_trace(student_solution_text: str, target_text: str = "") -> SymbolicTrace:
    """Build a partial symbolic trace from student free-form solution text."""
    lines = strip_reference_markers(student_solution_text)
    if not lines:
        return SymbolicTrace(
            steps=[],
            final_value=None,
            target_label=target_text or None,
            confidence=0.0,
            notes=["student_trace_missing"],
            provenance=ProvenanceSource.UNKNOWN,
        )

    # Student traces are lower-confidence and allow unknown operations.
    final_value = None
    trailing_numbers = _NUMBER_PATTERN.findall(lines[-1])
    if trailing_numbers:
        try:
            final_value = float(trailing_numbers[-1].replace(",", ""))
        except ValueError:
            final_value = None

    steps = []
    for idx, line in enumerate(lines, start=1):
        step = parse_trace_step(line, idx, final_value)
        step.provenance = (
            ProvenanceSource.PROBLEM_TEXT if step.operation == TraceOperation.UNKNOWN else ProvenanceSource.HEURISTIC
        )
        step.confidence = min(step.confidence, 0.8)
        steps.append(step)

    confidence = 0.0
    if steps:
        confidence = sum(step.confidence for step in steps) / len(steps)
    notes = [f"student_trace_steps={len(steps)}"]
    if any(step.operation == TraceOperation.UNKNOWN for step in steps):
        notes.append("student_trace_contains_unknown_steps")

    return SymbolicTrace(
        steps=steps,
        final_value=final_value,
        target_label=target_text or None,
        confidence=max(0.0, min(confidence, 1.0)),
        notes=notes,
        provenance=ProvenanceSource.HEURISTIC,
    )
