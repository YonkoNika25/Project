"""Baseline + Phase 2 diagnosis engine.

Phase 2 enhancement:
- Supports optional symbolic evidence (`SymbolicState`, `VerificationResult`) before LLM fallback.
"""
import json
import logging
import re
from typing import Optional

from src.models import (
    DiagnosisLabel,
    DiagnosisResult,
    ErrorLocalization,
    AnswerCheckResult,
    Correctness,
    SymbolicState,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

DIAGNOSIS_PROMPT_TEMPLATE = """You are a math tutoring diagnosis system. Analyze the student's error and classify it.

## Problem
{problem}

## Reference Solution
{reference_solution}
Reference Answer: {reference_answer}

## Student Answer
Raw: {student_raw}
Normalized Value: {student_value}
Correctness: {correctness}

## Symbolic Evidence (if available)
{symbolic_evidence}

## Task
Classify the student's error into exactly ONE of these categories:
- correct_answer: Student answered correctly
- arithmetic_error: Student understood the problem but made a calculation mistake
- quantity_relation_error: Student set up wrong relationships between quantities
- target_misunderstanding: Student solved for the wrong thing entirely
- unparseable_answer: Cannot determine what the student meant
- unknown_error: Error doesn't fit other categories

Also specify where the error occurred:
- none: No error (correct answer)
- final_computation: Error in the last calculation step
- intermediate_step: Error in a middle step
- target_selection: Student chose wrong target to solve for
- unknown: Cannot determine

Respond ONLY with valid JSON:
{{"label": "<label>", "localization": "<localization>", "explanation": "<brief explanation>"}}"""


def build_diagnosis_prompt(
    problem_text: str,
    reference_solution_text: str,
    reference_answer: float,
    student_raw: str,
    check_result: AnswerCheckResult,
    symbolic_state: Optional[SymbolicState] = None,
    verification_result: Optional[VerificationResult] = None,
) -> str:
    """Build the diagnosis prompt with all context."""
    symbolic_lines = []
    if symbolic_state is not None:
        symbolic_lines.append(
            f"state: op={symbolic_state.expected_operation.value}, quantities={len(symbolic_state.quantities)}, "
            f"builder_conf={symbolic_state.builder_confidence:.2f}"
        )
    if verification_result is not None:
        symbolic_lines.append(
            f"verify: status={verification_result.status.value}, predicted_label={verification_result.predicted_label}, "
            f"flags={verification_result.evidence_flags}, conf={verification_result.confidence:.2f}"
        )
    symbolic_evidence = "\n".join(symbolic_lines) if symbolic_lines else "none"

    return DIAGNOSIS_PROMPT_TEMPLATE.format(
        problem=problem_text,
        reference_solution=reference_solution_text,
        reference_answer=reference_answer,
        student_raw=student_raw,
        student_value=check_result.student_value,
        correctness=check_result.correctness.value,
        symbolic_evidence=symbolic_evidence,
    )


def parse_diagnosis_response(raw_response: str) -> DiagnosisResult:
    """Parse LLM response into a validated DiagnosisResult.

    Falls back to UnknownError if parsing fails.
    """
    try:
        json_match = re.search(r'\{[^{}]+\}', raw_response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in response")

        data = json.loads(json_match.group())
        label_str = data.get("label", "unknown_error")
        loc_str = data.get("localization", "unknown")
        explanation = data.get("explanation", "No explanation provided")

        try:
            label = DiagnosisLabel(label_str)
        except ValueError:
            logger.warning("Invalid label '%s', falling back to unknown_error", label_str)
            label = DiagnosisLabel.UNKNOWN_ERROR

        try:
            localization = ErrorLocalization(loc_str)
        except ValueError:
            logger.warning("Invalid localization '%s', falling back to unknown", loc_str)
            localization = ErrorLocalization.UNKNOWN

        return DiagnosisResult(
            label=label,
            localization=localization,
            explanation=explanation,
            confidence=0.7 if label != DiagnosisLabel.UNKNOWN_ERROR else 0.3,
            fallback_used=False,
        )

    except Exception as exc:
        logger.error("Failed to parse diagnosis response: %s", exc)
        return DiagnosisResult(
            label=DiagnosisLabel.UNKNOWN_ERROR,
            localization=ErrorLocalization.UNKNOWN,
            explanation=f"Failed to parse LLM response: {exc}",
            confidence=0.1,
            fallback_used=True,
        )


def diagnose_with_rules(check_result: AnswerCheckResult) -> Optional[DiagnosisResult]:
    """Simple rule-based diagnosis for cases that don't need LLM."""
    if check_result.correctness == Correctness.CORRECT:
        return DiagnosisResult(
            label=DiagnosisLabel.CORRECT_ANSWER,
            localization=ErrorLocalization.NONE,
            explanation="Student answered correctly",
            confidence=1.0,
        )

    if check_result.correctness == Correctness.UNPARSEABLE:
        return DiagnosisResult(
            label=DiagnosisLabel.UNPARSEABLE_ANSWER,
            localization=ErrorLocalization.UNKNOWN,
            explanation="Could not parse student answer for comparison",
            confidence=1.0,
        )

    return None


def diagnose_with_symbolic_evidence(
    check_result: AnswerCheckResult,
    verification_result: Optional[VerificationResult],
) -> Optional[DiagnosisResult]:
    """Phase 2: use symbolic verification as grounded diagnosis evidence."""
    if check_result.correctness != Correctness.INCORRECT or verification_result is None:
        return None

    if verification_result.status == VerificationStatus.CONFLICT and verification_result.predicted_label:
        return DiagnosisResult(
            label=verification_result.predicted_label,
            localization=verification_result.localization_hint,
            explanation=f"Grounded by verifier: {verification_result.explanation}",
            confidence=max(verification_result.confidence, 0.75),
            fallback_used=False,
        )

    if verification_result.status == VerificationStatus.VERIFIED:
        return DiagnosisResult(
            label=DiagnosisLabel.ARITHMETIC_ERROR,
            localization=ErrorLocalization.FINAL_COMPUTATION,
            explanation="Symbolic evidence suggests operation understanding is consistent; likely arithmetic slip.",
            confidence=max(verification_result.confidence, 0.65),
            fallback_used=False,
        )

    return None


def diagnose(
    problem_text: str,
    reference_solution_text: str,
    reference_answer: float,
    student_raw: str,
    check_result: AnswerCheckResult,
    llm_callable=None,
    symbolic_state: Optional[SymbolicState] = None,
    verification_result: Optional[VerificationResult] = None,
) -> DiagnosisResult:
    """Full diagnosis pipeline: rule-based, symbolic-evidence, then LLM."""
    rule_result = diagnose_with_rules(check_result)
    if rule_result is not None:
        return rule_result

    symbolic_result = diagnose_with_symbolic_evidence(
        check_result=check_result,
        verification_result=verification_result,
    )
    if symbolic_result is not None:
        return symbolic_result

    if llm_callable is None:
        return DiagnosisResult(
            label=DiagnosisLabel.UNKNOWN_ERROR,
            localization=ErrorLocalization.UNKNOWN,
            explanation="No LLM available for detailed diagnosis",
            confidence=0.1,
            fallback_used=True,
        )

    prompt = build_diagnosis_prompt(
        problem_text=problem_text,
        reference_solution_text=reference_solution_text,
        reference_answer=reference_answer,
        student_raw=student_raw,
        check_result=check_result,
        symbolic_state=symbolic_state,
        verification_result=verification_result,
    )

    try:
        raw_response = llm_callable(prompt)
        return parse_diagnosis_response(raw_response)
    except Exception as exc:
        logger.error("LLM diagnosis failed: %s", exc)
        return DiagnosisResult(
            label=DiagnosisLabel.UNKNOWN_ERROR,
            localization=ErrorLocalization.UNKNOWN,
            explanation=f"LLM diagnosis failed: {exc}",
            confidence=0.1,
            fallback_used=True,
        )
