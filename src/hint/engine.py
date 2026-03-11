"""Diagnosis-driven hint generation engine.

Generates pedagogical hints based on student diagnosis and defined policies.
"""
import json
import logging
import re
from typing import Optional, List

from src.models import (
    HintLevel,
    HintResult,
    DiagnosisResult,
    DiagnosisLabel,
)
from src.hint.policy import get_allowed_hint_levels

logger = logging.getLogger(__name__)

HINT_PROMPT_TEMPLATE = """You are an expert math tutor. Your goal is to provide a short, helpful hint to a student who made a mistake.

## Problem
{problem}

## Reference Solution (for your context only)
{reference_solution}

## Student Answer
{student_raw}

## Diagnosis of Student Error
Label: {diagnosis_label}
Internal Explanation: {diagnosis_explanation}

## Hint Level to Generate: {hint_level}
- conceptual: Focus on the high-level mathematical concept or strategy.
- relational: Focus on the relationship between quantities in the problem.
- next_step: Suggest a concrete next operation or step without giving the numbers.

## Critical Rules for the Hint
1. DO NOT give the final numeric answer.
2. DO NOT provide the full step-by-step solution.
3. Keep the hint shorter than 3 sentences.
4. Encourage the student to think.
5. Provide the hint in the same language as the student's answer if possible, otherwise use English.

Respond ONLY with valid JSON:
{{"hint_level": "{hint_level}", "hint_text": "<your hint here>"}}"""


def build_hint_prompt(
    problem_text: str,
    reference_solution_text: str,
    student_raw: str,
    diagnosis: DiagnosisResult,
    hint_level: HintLevel,
) -> str:
    """Build the hint generation prompt."""
    return HINT_PROMPT_TEMPLATE.format(
        problem=problem_text,
        reference_solution=reference_solution_text,
        student_raw=student_raw,
        diagnosis_label=diagnosis.label.value,
        diagnosis_explanation=diagnosis.explanation,
        hint_level=hint_level.value,
    )


def parse_hint_response(
    raw_response: str, 
    diagnosis_label: DiagnosisLabel,
    requested_level: HintLevel
) -> HintResult:
    """Parse LLM response into a validated HintResult."""
    try:
        # Extract JSON
        json_match = re.search(r'\{[^{}]+\}', raw_response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in response")

        data = json.loads(json_match.group())
        
        hint_text = data.get("hint_text", "").strip()
        if not hint_text:
            raise ValueError("Empty hint text in response")

        # Map level from response if valid, otherwise use requested
        level_str = data.get("hint_level", requested_level.value)
        try:
            hint_level = HintLevel(level_str)
        except ValueError:
            hint_level = requested_level

        return HintResult(
            hint_level=hint_level,
            hint_text=hint_text,
            generated_status="success",
            diagnosis_label_used=diagnosis_label,
            fallback_used=False,
        )

    except Exception as exc:
        logger.error("Failed to parse hint response: %s", exc)
        return HintResult(
            hint_level=requested_level,
            hint_text="An error occurred while generating the hint. Please try again.",
            generated_status="failure",
            diagnosis_label_used=diagnosis_label,
            fallback_used=True,
        )


def generate_hint(
    problem_text: str,
    reference_solution_text: str,
    student_raw: str,
    diagnosis: DiagnosisResult,
    llm_callable=None,
    preferred_level: Optional[HintLevel] = None,
) -> HintResult:
    """Full hint generation pipeline.

    Args:
        problem_text: The math problem.
        reference_solution_text: The gold solution.
        student_raw: Student's raw response.
        diagnosis: Structured diagnosis from the engine.
        llm_callable: Function that takes a prompt and returns a string.
        preferred_level: Optional preferred hint level. If not allowed, a default is used.

    Returns:
        HintResult with generated text.
    """
    allowed_levels = get_allowed_hint_levels(diagnosis.label)
    
    if not allowed_levels:
        return HintResult(
            hint_level=HintLevel.CONCEPTUAL,
            hint_text="Great job! Your answer is correct.",
            generated_status="success",
            diagnosis_label_used=diagnosis.label,
            fallback_used=False,
        )

    # Choose level: preferred if allowed, otherwise the first allowed one
    hint_level = preferred_level if preferred_level in allowed_levels else allowed_levels[0]

    if llm_callable is None:
        return HintResult(
            hint_level=hint_level,
            hint_text="Hinting engine is currently unavailable.",
            generated_status="failure",
            diagnosis_label_used=diagnosis.label,
            fallback_used=True,
        )

    prompt = build_hint_prompt(
        problem_text=problem_text,
        reference_solution_text=reference_solution_text,
        student_raw=student_raw,
        diagnosis=diagnosis,
        hint_level=hint_level,
    )

    try:
        raw_response = llm_callable(prompt)
        return parse_hint_response(raw_response, diagnosis.label, hint_level)
    except Exception as exc:
        logger.error("LLM hint generation failed: %s", exc)
        return HintResult(
            hint_level=hint_level,
            hint_text="I'm having trouble thinking of a hint right now. Maybe double check your math?",
            generated_status="failure",
            diagnosis_label_used=diagnosis.label,
            fallback_used=True,
        )
