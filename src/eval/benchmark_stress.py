"""Stress-test variant generation for benchmark robustness evaluation."""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.models import BenchmarkSample


@dataclass
class StressVariantCase:
    sample: BenchmarkSample
    variant_family: str
    variant_name: str


@dataclass
class StressGenerationBundle:
    original_samples: list[BenchmarkSample]
    stressed_samples: list[BenchmarkSample]
    variant_names: list[str]
    variant_cases: list[StressVariantCase]


_CUE_REPLACEMENTS = [
    ("in all", "overall"),
    ("altogether", "overall"),
    (" more ", " additional "),
    (" left", " still available"),
    (" difference ", " gap "),
    (" less than ", " below "),
]


def _clone_variant(
    sample: BenchmarkSample,
    *,
    sample_id_suffix: str,
    variant_family: str,
    variant_name: str,
    problem_text: str | None = None,
    student_answer_raw: str | None = None,
) -> BenchmarkSample:
    sample_data = sample.model_dump(mode="python")
    sample_data["sample_id"] = f"{sample.sample_id}{sample_id_suffix}"
    if problem_text is not None:
        sample_data["problem"]["text"] = problem_text
    if student_answer_raw is not None:
        sample_data["student_case"]["student_answer_raw"] = student_answer_raw
    sample_data["metadata"]["tags"] = list(sample.metadata.tags) + [
        "stress_eval",
        variant_family,
        variant_name,
    ]
    sample_data["metadata"]["notes"] = (
        (sample.metadata.notes + " " if sample.metadata.notes else "")
        + f"Stress variant generated with {variant_family}:{variant_name}."
    )
    return BenchmarkSample.model_validate(sample_data)


def _rewrite_problem_text(problem_text: str) -> tuple[str, str] | None:
    lowered = problem_text.lower()
    for source, target in _CUE_REPLACEMENTS:
        if source in lowered:
            start = lowered.index(source)
            end = start + len(source)
            rewritten = problem_text[:start] + target + problem_text[end:]
            return rewritten, f"cue_paraphrase:{source.strip()}->{target.strip()}"

    if problem_text.endswith("?"):
        return (
            "Consider the same situation carefully. " + problem_text,
            "context_prefix",
        )
    return None


def _rewrite_student_answer(student_answer_raw: str) -> tuple[str, str]:
    stripped = student_answer_raw.strip()
    if stripped.lower().startswith("i think the answer is"):
        value = stripped[len("I think the answer is"):].strip()
        return f"My final value is {value}", "answer_format_noise"
    return f"After checking, I wrote: {stripped}", "answer_format_noise"


def _reorder_context_sentences(problem_text: str) -> tuple[str, str] | None:
    sentences = re.split(r"(?<=[.!?])\s+", problem_text.strip())
    sentences = [s for s in sentences if s]
    if len(sentences) < 3:
        return None

    question_idx = next((idx for idx, sent in enumerate(sentences) if sent.endswith("?")), None)
    if question_idx is None or question_idx == 0:
        return None

    context = sentences[:question_idx]
    question = sentences[question_idx:]
    if len(context) < 2:
        return None

    reordered = " ".join(list(reversed(context)) + question)
    if reordered == problem_text:
        return None
    return reordered, "context_reorder"


def _rephrase_question(problem_text: str) -> tuple[str, str] | None:
    sentences = re.split(r"(?<=[.!?])\s+", problem_text.strip())
    sentences = [s for s in sentences if s]
    if not sentences:
        return None

    question = sentences[-1]
    rewritten_question = question
    replacements = [
        (r"^How many ", "What is the number of "),
        (r" now\?$", " at this point?"),
        (r" left\?$", " still available?"),
        (r" in all\?$", " overall?"),
    ]
    for pattern, replacement in replacements:
        rewritten_question = re.sub(pattern, replacement, rewritten_question, flags=re.IGNORECASE)

    if rewritten_question == question:
        return None

    rewritten = " ".join(sentences[:-1] + [rewritten_question])
    return rewritten, "question_rephrase"


def make_stress_variant(sample: BenchmarkSample) -> tuple[BenchmarkSample, str]:
    """Legacy combined stress variant retained for compatibility/tests."""
    problem_variant = _rewrite_problem_text(sample.problem.text)
    student_answer_raw, answer_variant = _rewrite_student_answer(sample.student_case.student_answer_raw)

    rewritten_problem = sample.problem.text
    problem_variant_name = "identity_problem"
    if problem_variant is not None:
        rewritten_problem, problem_variant_name = problem_variant

    variant_name = f"{problem_variant_name}+{answer_variant}"
    variant = _clone_variant(
        sample,
        sample_id_suffix="__stress",
        variant_family="combined_surface",
        variant_name=variant_name,
        problem_text=rewritten_problem,
        student_answer_raw=student_answer_raw,
    )
    return variant, variant_name


def generate_stress_variants(samples: list[BenchmarkSample]) -> StressGenerationBundle:
    variant_cases: list[StressVariantCase] = []

    for sample in samples:
        combined_variant, combined_name = make_stress_variant(sample)
        variant_cases.append(
            StressVariantCase(
                sample=combined_variant,
                variant_family="combined_surface",
                variant_name=combined_name,
            )
        )

        problem_variant = _rewrite_problem_text(sample.problem.text)
        if problem_variant is not None:
            rewritten_problem, variant_name = problem_variant
            variant_cases.append(
                StressVariantCase(
                    sample=_clone_variant(
                        sample,
                        sample_id_suffix="__stress__problem_surface",
                        variant_family="problem_surface",
                        variant_name=variant_name,
                        problem_text=rewritten_problem,
                    ),
                    variant_family="problem_surface",
                    variant_name=variant_name,
                )
            )

        question_variant = _rephrase_question(sample.problem.text)
        if question_variant is not None:
            rewritten_problem, variant_name = question_variant
            variant_cases.append(
                StressVariantCase(
                    sample=_clone_variant(
                        sample,
                        sample_id_suffix="__stress__question_rephrase",
                        variant_family="question_rephrase",
                        variant_name=variant_name,
                        problem_text=rewritten_problem,
                    ),
                    variant_family="question_rephrase",
                    variant_name=variant_name,
                )
            )

        context_variant = _reorder_context_sentences(sample.problem.text)
        if context_variant is not None:
            rewritten_problem, variant_name = context_variant
            variant_cases.append(
                StressVariantCase(
                    sample=_clone_variant(
                        sample,
                        sample_id_suffix="__stress__context_reorder",
                        variant_family="context_reorder",
                        variant_name=variant_name,
                        problem_text=rewritten_problem,
                    ),
                    variant_family="context_reorder",
                    variant_name=variant_name,
                )
            )

        rewritten_answer, variant_name = _rewrite_student_answer(sample.student_case.student_answer_raw)
        variant_cases.append(
            StressVariantCase(
                sample=_clone_variant(
                    sample,
                    sample_id_suffix="__stress__answer_format",
                    variant_family="answer_format",
                    variant_name=variant_name,
                    student_answer_raw=rewritten_answer,
                ),
                variant_family="answer_format",
                variant_name=variant_name,
            )
        )

    stressed_samples = [case.sample for case in variant_cases]
    variant_names = [case.variant_name for case in variant_cases]
    return StressGenerationBundle(
        original_samples=samples,
        stressed_samples=stressed_samples,
        variant_names=variant_names,
        variant_cases=variant_cases,
    )
