from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.diagnosis import diagnose
from src.evidence import build_diagnosis_evidence
from src.formalizer import formalize_problem, formalize_student_work
from src.hint import build_hint_result
from src.llm import build_default_llm_client
from src.models import HintMode
from src.pedagogy import build_hint_plan
from src.runtime import build_canonical_reference


ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "data" / "hint_diagnosis_stress_200.jsonl"
OUTPUT_DIR = ROOT / "results"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _match(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def _base_result_row(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": sample["sample_id"],
        "problem_id": sample["problem_id"],
        "category": sample["category"],
        "difficulty": sample["difficulty"],
        "variant_type": sample["variant_type"],
        "expected_correctness": sample["expected_correctness"],
        "gold_final_answer": sample["gold_final_answer"],
        "problem_formalization_ok": False,
        "reference_build_ok": False,
        "student_formalization_ok": False,
        "evidence_build_ok": False,
        "diagnosis_ok": False,
        "hint_ok": False,
        "failing_stage": None,
        "error_message": None,
    }


def _build_problem_context(
    sample: dict[str, Any],
    llm_client,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "problem_formalization_ok": False,
        "reference_build_ok": False,
        "failing_stage": None,
        "error_message": None,
        "problem": None,
        "reference": None,
    }

    try:
        problem = formalize_problem(sample["problem_text"], llm_client=llm_client)
        context["problem_formalization_ok"] = True
        context["problem"] = problem
    except Exception as exc:  # noqa: BLE001
        context["failing_stage"] = "problem_formalization"
        context["error_message"] = str(exc)
        return context

    try:
        reference = build_canonical_reference(problem)
        context["reference_build_ok"] = True
        context["reference"] = reference
    except Exception as exc:  # noqa: BLE001
        context["failing_stage"] = "reference_build"
        context["error_message"] = str(exc)
        return context

    return context


def run_sample(
    sample: dict[str, Any],
    llm_client,
    problem_context_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    row = _base_result_row(sample)

    problem_id = sample["problem_id"]
    if problem_id not in problem_context_cache:
        problem_context_cache[problem_id] = _build_problem_context(sample, llm_client=llm_client)
        row["problem_context_cached"] = False
    else:
        row["problem_context_cached"] = True

    context = problem_context_cache[problem_id]
    row["problem_formalization_ok"] = context["problem_formalization_ok"]
    row["reference_build_ok"] = context["reference_build_ok"]

    if context["failing_stage"] is not None:
        row["failing_stage"] = context["failing_stage"]
        row["error_message"] = context["error_message"]
        return row

    problem = context["problem"]
    reference = context["reference"]

    try:
        student = formalize_student_work(
            sample["student_answer"],
            problem=problem,
            reference=reference,
            llm_client=llm_client,
        )
        row["student_formalization_ok"] = True
        row["student_mode"] = student.mode.value
        row["student_normalized_final_answer"] = student.normalized_final_answer
    except Exception as exc:  # noqa: BLE001
        row["failing_stage"] = "student_formalization"
        row["error_message"] = str(exc)
        return row

    try:
        evidence = build_diagnosis_evidence(problem, reference, student)
        row["evidence_build_ok"] = True
        row["first_divergence_step_id"] = evidence.first_divergence_step_id
        row["likely_error_mechanisms"] = list(evidence.likely_error_mechanisms)
    except Exception as exc:  # noqa: BLE001
        row["failing_stage"] = "evidence"
        row["error_message"] = str(exc)
        return row

    try:
        diagnosis = diagnose(evidence, llm_client=llm_client)
        row["diagnosis_ok"] = True
        row["diagnosis_label"] = diagnosis.diagnosis_label.value
        row["diagnosis_confidence"] = diagnosis.confidence
    except Exception as exc:  # noqa: BLE001
        row["failing_stage"] = "diagnosis"
        row["error_message"] = str(exc)
        return row

    try:
        plan = build_hint_plan(problem, reference, diagnosis)
        hint = build_hint_result(
            problem,
            reference,
            diagnosis,
            plan,
            hint_mode=HintMode.NORMAL,
            llm_client=llm_client,
        )
        row["hint_ok"] = True
        row["teacher_move"] = plan.teacher_move.value
        row["hint_level"] = plan.hint_level.value
        row["hint_text"] = hint.hint_text
        row["hint_verification_passed"] = hint.verification_passed
        row["hint_violated_rules"] = list(hint.violated_rules)
        row["hint_notes"] = list(hint.notes)
    except Exception as exc:  # noqa: BLE001
        row["failing_stage"] = "hint"
        row["error_message"] = str(exc)
        return row

    row["pipeline_detected_final_correct"] = _match(row.get("student_normalized_final_answer"), sample["gold_final_answer"])
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sample_count": len(rows),
        "unique_problem_count": len({row["problem_id"] for row in rows}),
        "stage_counts": dict(Counter(row["failing_stage"] or "completed" for row in rows)),
        "category_counts": dict(Counter(row["category"] for row in rows)),
        "diagnosis_counts": dict(Counter(row.get("diagnosis_label", "missing") for row in rows)),
        "hint_verification_failures": sum(1 for row in rows if row.get("hint_ok") and not row.get("hint_verification_passed", False)),
        "problem_context_cache_hits": sum(1 for row in rows if row.get("problem_context_cached") is True),
        "final_correctness_agreement": sum(
            1
            for row in rows
            if row.get("pipeline_detected_final_correct") is not None
            and row.get("pipeline_detected_final_correct") == row["expected_correctness"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--use-llm", dest="use_llm", action="store_true")
    parser.add_argument("--no-llm", dest="use_llm", action="store_false")
    parser.set_defaults(use_llm=True)
    parser.add_argument("--output-prefix", default="hint_diagnosis_benchmark")
    args = parser.parse_args()

    rows = _load_jsonl(args.dataset)
    if args.limit is not None:
        rows = rows[: args.limit]

    llm_client = build_default_llm_client() if args.use_llm else None
    problem_context_cache: dict[str, dict[str, Any]] = {}
    results = [
        run_sample(
            row,
            llm_client=llm_client,
            problem_context_cache=problem_context_cache,
        )
        for row in rows
    ]
    summary = summarize(results)
    summary["llm_enabled"] = args.use_llm

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUTPUT_DIR / f"{args.output_prefix}_results.jsonl"
    summary_path = OUTPUT_DIR / f"{args.output_prefix}_summary.json"
    with results_path.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Benchmark run completed.")
    print(f"Results rows: {len(results)}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
