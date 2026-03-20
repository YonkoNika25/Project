"""Benchmark draft generation utilities for solver-grounded tutoring evaluation."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from src.models import (
    BenchmarkMetadata,
    BenchmarkProblem,
    BenchmarkQuantityAnnotation,
    BenchmarkSample,
    DiagnosisLabel,
    ErrorLocalization,
    GoldDiagnosisAnnotation,
    GoldReferenceAnnotation,
    OperationType,
    ProblemRecord,
    StudentCase,
    SymbolicAnnotation,
)
from src.verification.symbolic_state_builder import build_symbolic_state

_TOTAL_CUES = ("total", "altogether", "in all", "sum")
_REMAINING_CUES = ("left", "remain", "remaining", "after giving", "after spending")
_COMPARISON_CUES = ("how many more", "difference", "fewer", "less", "more than")


@dataclass
class ProblemSelectionScore:
    """Heuristic score used to select clean base problems for the first benchmark subset."""

    problem_id: str
    score: int
    reasons: List[str] = field(default_factory=list)


@dataclass
class BenchmarkGenerationBundle:
    """Generated benchmark draft plus selection metadata."""

    selected_problems: List[ProblemRecord]
    selection_scores: List[ProblemSelectionScore]
    samples: List[BenchmarkSample]


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _extract_answer_span(answer_text: str, fallback_value: float) -> str:
    match = re.search(r"####\s*([^\n]+)", answer_text)
    if match:
        return match.group(1).strip()
    return _format_number(fallback_value)


def _estimate_difficulty(problem_text: str, quantity_count: int) -> str:
    word_count = len(problem_text.split())
    if quantity_count >= 4 or word_count >= 45:
        return "hard"
    if quantity_count >= 3 or word_count >= 25:
        return "medium"
    return "easy"


def _estimate_requires_multi_step(problem_text: str, solution_text: str, quantity_count: int) -> bool:
    lower = problem_text.lower()
    multi_step_cues = ("twice", "double", "triple", "half", "quarter", "%", "percent", "each", "per")

    if quantity_count >= 3:
        return True
    if solution_text.count("<<") >= 2:
        return True
    if sum(1 for cue in multi_step_cues if cue in lower) >= 1 and quantity_count >= 2:
        return True
    return False


def _infer_target_type(problem_text: str) -> str:
    lower = problem_text.lower()
    if any(cue in lower for cue in _REMAINING_CUES):
        return "remaining_quantity"
    if any(cue in lower for cue in _TOTAL_CUES):
        return "total_quantity"
    if any(cue in lower for cue in _COMPARISON_CUES):
        return "comparison_quantity"
    return "unknown_target"


def _expected_relation_name(expected_operation: OperationType) -> str:
    if expected_operation == OperationType.ADDITIVE:
        return "additive_composition"
    if expected_operation == OperationType.SUBTRACTIVE:
        return "subtractive_comparison"
    return "unknown_relation"


def _quantity_role(expected_operation: OperationType, index: int) -> str:
    if expected_operation == OperationType.ADDITIVE:
        return "base_quantity" if index == 0 else "added_quantity"
    if expected_operation == OperationType.SUBTRACTIVE:
        return "initial_quantity" if index == 0 else "removed_quantity"
    return f"quantity_{index}"


def _build_problem_annotation(record: ProblemRecord) -> BenchmarkProblem:
    state = build_symbolic_state(record.problem, record.gold_answer_text)
    return BenchmarkProblem(
        text=record.problem,
        difficulty=_estimate_difficulty(record.problem, len(state.quantities)),
        requires_multi_step=_estimate_requires_multi_step(
            record.problem,
            record.gold_answer_text,
            len(state.quantities),
        ),
    )


def _build_symbolic_annotation(record: ProblemRecord) -> SymbolicAnnotation:
    state = build_symbolic_state(record.problem, record.gold_answer_text)
    quantities = [
        BenchmarkQuantityAnnotation(
            value=fact.value,
            surface_text=fact.surface_form,
            role=_quantity_role(state.expected_operation, idx),
            provenance="problem_text",
        )
        for idx, fact in enumerate(state.quantities)
    ]
    return SymbolicAnnotation(
        quantities=quantities,
        target_text=state.target_text,
        target_type=_infer_target_type(record.problem),
        expected_relation=_expected_relation_name(state.expected_operation),
        expected_operation=state.expected_operation,
    )


def _has_target_candidate(record: ProblemRecord) -> bool:
    state = build_symbolic_state(record.problem, record.gold_answer_text)
    return _find_target_misunderstanding_value(state, record.gold_answer_value) is not None


def score_problem_for_benchmark(record: ProblemRecord) -> ProblemSelectionScore:
    """Score a GSM8K problem for inclusion in the initial benchmark subset."""
    state = build_symbolic_state(record.problem, record.gold_answer_text)
    lower = record.problem.lower()
    score = 0
    reasons: List[str] = []

    target_score = 0
    if "?" in record.problem:
        target_score += 1
    if state.target_text:
        target_score += 1
    if any(cue in lower for cue in _TOTAL_CUES + _REMAINING_CUES + _COMPARISON_CUES):
        target_score += 1
    score += target_score
    reasons.append(f"target_clarity={target_score}")

    relation_score = 0
    if len(state.quantities) >= 2:
        relation_score += 1
    if state.expected_operation != OperationType.UNKNOWN:
        relation_score += 2
    score += relation_score
    reasons.append(f"relation_clarity={relation_score}")

    symbolic_score = 0
    if len(state.quantities) >= 2:
        symbolic_score += 1
    if 2 <= len(state.quantities) <= 4:
        symbolic_score += 1
    if state.builder_confidence >= 0.7:
        symbolic_score += 1
    score += symbolic_score
    reasons.append(f"symbolic_compatibility={symbolic_score}")

    generation_score = 0
    if len(state.quantities) >= 2:
        generation_score += 1
    if state.expected_operation != OperationType.UNKNOWN:
        generation_score += 1
    if _has_target_candidate(record):
        generation_score += 1
    score += generation_score
    reasons.append(f"case_generation_potential={generation_score}")

    audit_score = 0
    word_count = len(record.problem.split())
    if word_count <= 45:
        audit_score += 1
    if len(state.quantities) <= 4:
        audit_score += 1
    if state.target_text and state.expected_operation != OperationType.UNKNOWN:
        audit_score += 1
    score += audit_score
    reasons.append(f"auditability={audit_score}")

    return ProblemSelectionScore(problem_id=record.id, score=score, reasons=reasons)


def select_base_problems(
    records: Iterable[ProblemRecord],
    limit: int = 30,
) -> tuple[List[ProblemRecord], List[ProblemSelectionScore]]:
    """Select the cleanest base problems for the first benchmark draft."""
    scored = []
    for record in records:
        score = score_problem_for_benchmark(record)
        scored.append((record, score))

    scored.sort(key=lambda item: (-item[1].score, item[0].id))
    selected_pairs = scored[:limit]
    selected_records = [record for record, _ in selected_pairs]
    selection_scores = [score for _, score in selected_pairs]
    return selected_records, selection_scores


def _assign_splits(records: List[ProblemRecord]) -> dict[str, str]:
    total = len(records)
    if total == 0:
        return {}

    train_cut = math.ceil(total * 0.5)
    dev_cut = train_cut + math.ceil(total * 0.3)

    split_map: dict[str, str] = {}
    for index, record in enumerate(records):
        if index < train_cut:
            split_map[record.id] = "train_build"
        elif index < dev_cut:
            split_map[record.id] = "dev_audit"
        else:
            split_map[record.id] = "test_paper"
    return split_map


def _make_gold_reference(record: ProblemRecord) -> GoldReferenceAnnotation:
    return GoldReferenceAnnotation(
        final_answer=record.gold_answer_value,
        solution_text=record.gold_answer_text.strip(),
        answer_format="integer" if record.gold_answer_value.is_integer() else "numeric",
        answer_span=_extract_answer_span(record.gold_answer_text, record.gold_answer_value),
    )


def _make_metadata(
    split: str,
    label: DiagnosisLabel,
    generation_method: str,
    expected_operation: OperationType,
) -> BenchmarkMetadata:
    return BenchmarkMetadata(
        created_by="benchmark_generator",
        review_status="draft",
        reviewers=[],
        notes="Synthetic benchmark draft generated automatically. Human audit required before evaluation use.",
        tags=[
            split,
            label.value,
            generation_method,
            expected_operation.value,
        ],
    )


def _make_gold_diagnosis(
    label: DiagnosisLabel,
    localization: ErrorLocalization,
    rationale: str,
) -> GoldDiagnosisAnnotation:
    confidence_map = {
        DiagnosisLabel.CORRECT_ANSWER: 1.0,
        DiagnosisLabel.ARITHMETIC_ERROR: 0.85,
        DiagnosisLabel.QUANTITY_RELATION_ERROR: 0.9,
        DiagnosisLabel.TARGET_MISUNDERSTANDING: 0.8,
        DiagnosisLabel.UNKNOWN_ERROR: 0.5,
        DiagnosisLabel.UNPARSEABLE_ANSWER: 0.75,
    }
    return GoldDiagnosisAnnotation(
        primary_label=label,
        secondary_label=None,
        localization=localization,
        confidence=confidence_map[label],
        rationale=rationale,
        review_status="draft",
        review_notes="Synthetic draft label. Confirm during human audit.",
    )


def _build_sample(
    record: ProblemRecord,
    split: str,
    label: DiagnosisLabel,
    localization: ErrorLocalization,
    student_value: float,
    generation_method: str,
    rationale: str,
    case_index: int,
) -> BenchmarkSample:
    symbolic_annotation = _build_symbolic_annotation(record)
    sample_id = f"{record.id}__{label.value}__{case_index:02d}"
    student_answer_text = f"I think the answer is {_format_number(student_value)}."

    return BenchmarkSample(
        sample_id=sample_id,
        split=split,
        source_dataset=str(record.metadata.get("source", "gsm8k")),
        source_problem_id=record.id,
        source_type="synthetic_draft",
        problem=_build_problem_annotation(record),
        gold_reference=_make_gold_reference(record),
        student_case=StudentCase(
            student_answer_raw=student_answer_text,
            student_answer_value=student_value,
            answer_source="synthetic",
            error_generation_method=generation_method,
            student_rationale=None,
        ),
        gold_diagnosis=_make_gold_diagnosis(label, localization, rationale),
        gold_hint=None,
        symbolic_annotation=symbolic_annotation,
        metadata=_make_metadata(
            split=split,
            label=label,
            generation_method=generation_method,
            expected_operation=symbolic_annotation.expected_operation,
        ),
    )


def _find_arithmetic_error_value(
    gold_answer: float,
    forbidden_values: Iterable[float] = (),
) -> tuple[float, str]:
    forbidden = {round(value, 9) for value in forbidden_values}
    step = max(1.0, round(abs(gold_answer) * 0.1)) if abs(gold_answer) >= 10 else 1.0
    candidates = [
        gold_answer + step,
        gold_answer - step,
        gold_answer + 2.0,
        gold_answer - 2.0,
    ]
    for candidate in candidates:
        if candidate < 0 and gold_answer >= 0:
            continue
        if round(candidate, 9) == round(gold_answer, 9):
            continue
        if round(candidate, 9) in forbidden:
            continue
        return candidate, "near_miss_final_computation"
    return gold_answer + 1.0, "near_miss_final_computation"


def _find_relation_error_value(
    state_operation: OperationType,
    quantities: List[float],
    gold_answer: float,
) -> Optional[tuple[float, str]]:
    if len(quantities) < 2 or state_operation == OperationType.UNKNOWN:
        return None

    candidates: List[tuple[float, str]] = []
    if state_operation == OperationType.ADDITIVE:
        if len(quantities) >= 3:
            candidates.extend(
                [
                    (sum(quantities[:2]), "partial_sum_only"),
                    (abs(quantities[0] - quantities[1]), "difference_instead_of_sum"),
                    (abs(max(quantities) - min(quantities)), "comparison_instead_of_total"),
                ]
            )
        else:
            candidates.extend(
                [
                    (abs(quantities[0] - quantities[1]), "difference_instead_of_sum"),
                    (abs(max(quantities) - min(quantities)), "difference_instead_of_sum"),
                ]
            )
    elif state_operation == OperationType.SUBTRACTIVE:
        candidates.extend(
            [
                (quantities[0] - quantities[1], "first_subtraction_only"),
                (sum(quantities), "sum_instead_of_difference"),
                (sum(quantities[1:]), "drop_initial_quantity"),
            ]
        )

    for candidate, method in candidates:
        if candidate < 0 and gold_answer >= 0:
            continue
        if round(candidate, 9) != round(gold_answer, 9):
            return candidate, method
    return None


def _find_target_misunderstanding_value(
    state,
    gold_answer: float,
) -> Optional[tuple[float, str]]:
    values = [fact.value for fact in state.quantities]
    if not values:
        return None

    preferred_order: List[float] = []
    if state.expected_operation == OperationType.SUBTRACTIVE and len(values) >= 2:
        preferred_order.extend([values[1], values[0]])
    elif state.expected_operation == OperationType.ADDITIVE:
        preferred_order.extend([values[0], values[-1]])
    preferred_order.extend(values)

    seen = set()
    for candidate in preferred_order:
        rounded = round(candidate, 9)
        if rounded in seen:
            continue
        seen.add(rounded)
        if rounded != round(gold_answer, 9):
            return candidate, "select_non_target_quantity"
    return None


def generate_candidate_samples(
    record: ProblemRecord,
    split: str,
    max_cases_per_problem: int = 3,
    problem_index: int = 0,
) -> List[BenchmarkSample]:
    """Generate synthetic benchmark draft cases for one base problem."""
    if max_cases_per_problem <= 0:
        return []

    state = build_symbolic_state(record.problem, record.gold_answer_text)
    quantities = [fact.value for fact in state.quantities]

    relation_candidate = _find_relation_error_value(
        state_operation=state.expected_operation,
        quantities=quantities,
        gold_answer=record.gold_answer_value,
    )
    target_candidate = _find_target_misunderstanding_value(state, record.gold_answer_value)
    forbidden = []
    if relation_candidate is not None:
        forbidden.append(relation_candidate[0])
    if target_candidate is not None:
        forbidden.append(target_candidate[0])
    arithmetic_value, arithmetic_method = _find_arithmetic_error_value(
        record.gold_answer_value,
        forbidden_values=forbidden,
    )

    planned_cases = [
        (
            DiagnosisLabel.CORRECT_ANSWER,
            ErrorLocalization.NONE,
            record.gold_answer_value,
            "gold_reference_copy",
            "Student answer matches the correct target quantity exactly.",
        ),
        (
            DiagnosisLabel.ARITHMETIC_ERROR,
            ErrorLocalization.FINAL_COMPUTATION,
            arithmetic_value,
            arithmetic_method,
            "Student answer stays near the correct result but misses the final computation.",
        ),
    ]

    optional_cases = []
    if relation_candidate is not None:
        optional_cases.append(
            (
                DiagnosisLabel.QUANTITY_RELATION_ERROR,
                ErrorLocalization.COMBINING_QUANTITIES,
                relation_candidate[0],
                relation_candidate[1],
                "Student answer matches a wrong quantity-combination strategy rather than the intended relation.",
            )
        )
    if target_candidate is not None:
        optional_cases.append(
            (
                DiagnosisLabel.TARGET_MISUNDERSTANDING,
                ErrorLocalization.TARGET_SELECTION,
                target_candidate[0],
                target_candidate[1],
                "Student answer corresponds to a visible quantity in the problem but not the quantity the question asks for.",
            )
        )

    if problem_index % 2 == 1:
        optional_cases.sort(
            key=lambda item: 0 if item[0] == DiagnosisLabel.TARGET_MISUNDERSTANDING else 1
        )

    planned_cases.extend(optional_cases)
    planned_cases = planned_cases[:max_cases_per_problem]

    return [
        _build_sample(
            record=record,
            split=split,
            label=label,
            localization=localization,
            student_value=value,
            generation_method=generation_method,
            rationale=rationale,
            case_index=case_index,
        )
        for case_index, (label, localization, value, generation_method, rationale) in enumerate(planned_cases, start=1)
    ]


def generate_benchmark_bundle(
    records: Iterable[ProblemRecord],
    base_problem_limit: int = 30,
    max_cases_per_problem: int = 3,
) -> BenchmarkGenerationBundle:
    """Generate the first-round benchmark draft from a pool of base problems."""
    selected_problems, selection_scores = select_base_problems(records, limit=base_problem_limit)
    split_map = _assign_splits(selected_problems)

    samples: List[BenchmarkSample] = []
    for index, record in enumerate(selected_problems):
        split = split_map.get(record.id, "train_build")
        samples.extend(
            generate_candidate_samples(
                record=record,
                split=split,
                max_cases_per_problem=max_cases_per_problem,
                problem_index=index,
            )
        )

    return BenchmarkGenerationBundle(
        selected_problems=selected_problems,
        selection_scores=selection_scores,
        samples=samples,
    )
