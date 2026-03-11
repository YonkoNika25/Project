"""Baseline prompt-based diagnosis engine.

Analyzes the problem, student answer, answer-check result, and reference solution
to assign a structured DiagnosisResult using the predefined taxonomy.
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
) -> str:
    """Build the diagnosis prompt with all context."""
    return DIAGNOSIS_PROMPT_TEMPLATE.format(
        problem=problem_text,
        reference_solution=reference_solution_text,
        reference_answer=reference_answer,
        student_raw=student_raw,
        student_value=check_result.student_value,
        correctness=check_result.correctness.value,
    )


def parse_diagnosis_response(raw_response: str) -> DiagnosisResult:
    """Parse LLM response into a validated DiagnosisResult.

    Falls back to UnknownError if parsing fails.
    """
    try:
        # Try to extract JSON from the response
        json_match = re.search(r'\{[^{}]+\}', raw_response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in response")

        data = json.loads(json_match.group())

        label_str = data.get("label", "unknown_error")
        loc_str = data.get("localization", "unknown")
        explanation = data.get("explanation", "No explanation provided")

        # Validate label
        try:
            label = DiagnosisLabel(label_str)
        except ValueError:
            logger.warning("Invalid label '%s', falling back to unknown_error", label_str)
            label = DiagnosisLabel.UNKNOWN_ERROR

        # Validate localization
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


def diagnose_with_rules(check_result: AnswerCheckResult) -> DiagnosisResult:
    """Simple rule-based diagnosis for cases that don't need LLM.

    Used for correct answers and unparseable inputs.
    """
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

    # For incorrect answers, we need the LLM — return None to signal this
    return None


def diagnose(
    problem_text: str,
    reference_solution_text: str,
    reference_answer: float,
    student_raw: str,
    check_result: AnswerCheckResult,
    llm_callable=None,
) -> DiagnosisResult:
    """Full diagnosis pipeline: rule-based first, then LLM if needed.

    Args:
        problem_text: The math problem.
        reference_solution_text: Full reference solution text.
        reference_answer: Normalized reference answer.
        student_raw: Raw student answer text.
        check_result: Result of answer checking.
        llm_callable: Optional callable(prompt) -> str for LLM diagnosis.
                      If None and LLM is needed, falls back to UnknownError.

    Returns:
        DiagnosisResult with taxonomy label.
    """
    # Try rule-based first
    rule_result = diagnose_with_rules(check_result)
    if rule_result is not None:
        return rule_result

    # Need LLM for incorrect answers
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
