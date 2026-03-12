"""Small evaluation harness for the baseline pipeline.

Usage:
  python run_eval.py --split test --limit 50
"""
import argparse
import logging
from collections import Counter

from src.checker.answer_checker import check_answer
from src.dataset.gsm8k_loader import load_gsm8k_from_huggingface
from src.diagnosis.engine import diagnose
from src.diagnosis.evaluation import (
    evaluate_diagnoses,
    compute_confidence_calibration,
    compare_symbolic_ablation,
)
from src.hint.controller import HintController
from src.hint.verifier import verify_hint_alignment
from src.models import (
    SolverResponse,
    SolverStatus,
    DiagnosisLabel,
    DiagnosisResult,
    ErrorLocalization,
)
from src.solver.reference_parser import parse_solver_response, ParseStatus
from src.utils.llm_client import hf_llm_adapter
from src.verification.symbolic_state_builder import build_symbolic_state
from src.verification.symbolic_verifier import verify_symbolic_consistency
from src.eval.audit_io import load_label_map, write_audit_jsonl

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _unknown_diag(explanation: str) -> DiagnosisResult:
    return DiagnosisResult(
        label=DiagnosisLabel.UNKNOWN_ERROR,
        localization=ErrorLocalization.UNKNOWN,
        explanation=explanation,
        confidence=0.1,
        fallback_used=True,
    )


def evaluate(
    split: str,
    limit: int,
    audit_labels: str | None = None,
    audit_output: str | None = None,
    calibration_bins: int = 5,
    run_symbolic_ablation: bool = False,
) -> None:
    records, report = load_gsm8k_from_huggingface(split=split)
    records = records[:limit]

    label_map = load_label_map(audit_labels) if audit_labels else {}

    parse_success = 0
    reference_correct = 0
    spoiler_free = 0
    hint_alignment_ok = 0
    diagnosis_counter: Counter[str] = Counter()
    verification_counter: Counter[str] = Counter()

    diagnosis_predictions: list[tuple[str, DiagnosisResult]] = []
    diagnosis_predictions_no_symbolic: list[tuple[str, DiagnosisResult]] = []
    audit_rows: list[dict] = []

    hint_controller = HintController(llm_callable=hf_llm_adapter)

    for idx, rec in enumerate(records, start=1):
        solve_prompt = (
            "Solve this math problem step by step and end with '#### <answer>'.\n\n"
            f"Problem: {rec.problem}"
        )
        raw_solve = hf_llm_adapter(solve_prompt)

        solver_response = SolverResponse(
            raw_text=raw_solve,
            status=SolverStatus.SUCCESS,
            model_name="qwen/qwen2.5-7b-instruct",
            latency_ms=0.0,
            attempt_count=1,
        )
        parse_result = parse_solver_response(solver_response)

        if parse_result.status != ParseStatus.SUCCESS or parse_result.reference is None:
            diag_res = _unknown_diag(f"Parse failed: {parse_result.status.value}")
            diagnosis_predictions.append((rec.id, diag_res))
            diagnosis_counter[diag_res.label.value] += 1
            logger.warning("[%d/%d] parse failed: %s", idx, len(records), parse_result.status.value)
            audit_rows.append(
                {
                    "problem_id": rec.id,
                    "parse_status": parse_result.status.value,
                    "verification_status": "not_run",
                    "diagnosis_label": diag_res.label.value,
                    "hint_level": None,
                    "fallback_used": True,
                }
            )
            continue

        parse_success += 1
        ref_sol = parse_result.reference
        if abs(ref_sol.final_answer - rec.gold_answer_value) < 1e-9:
            reference_correct += 1

        student_answer = f"I think the answer is {ref_sol.final_answer - 1}."
        check_res = check_answer(student_answer, ref_sol.final_answer)

        symbolic_state = build_symbolic_state(rec.problem, ref_sol.solution_text)
        verification_result = verify_symbolic_consistency(symbolic_state, check_res)
        verification_counter[verification_result.status.value] += 1

        diag_res = diagnose(
            problem_text=rec.problem,
            reference_solution_text=ref_sol.solution_text,
            reference_answer=ref_sol.final_answer,
            student_raw=student_answer,
            check_result=check_res,
            llm_callable=hf_llm_adapter,
            symbolic_state=symbolic_state,
            verification_result=verification_result,
        )
        diagnosis_predictions.append((rec.id, diag_res))
        diagnosis_counter[diag_res.label.value] += 1

        if run_symbolic_ablation:
            diag_no_symbolic = diagnose(
                problem_text=rec.problem,
                reference_solution_text=ref_sol.solution_text,
                reference_answer=ref_sol.final_answer,
                student_raw=student_answer,
                check_result=check_res,
                llm_callable=hf_llm_adapter,
            )
            diagnosis_predictions_no_symbolic.append((rec.id, diag_no_symbolic))

        hint_res = hint_controller.get_hint(
            problem_text=rec.problem,
            reference_solution_text=ref_sol.solution_text,
            reference_answer=ref_sol.final_answer,
            student_raw=student_answer,
            diagnosis=diag_res,
            verification_result=verification_result,
        )
        if not hint_res.fallback_used:
            spoiler_free += 1

        aligned = verify_hint_alignment(
            hint_res.hint_text,
            diagnosis_label=diag_res.label,
            expected_level=hint_res.hint_level,
        )
        if aligned:
            hint_alignment_ok += 1

        audit_rows.append(
            {
                "problem_id": rec.id,
                "parse_status": parse_result.status.value,
                "verification_status": verification_result.status.value,
                "diagnosis_label": diag_res.label.value,
                "hint_level": hint_res.hint_level.value,
                "fallback_used": hint_res.fallback_used,
                "hint_aligned": aligned,
                "expected_label": label_map.get(rec.id).value if rec.id in label_map else None,
                "diagnosis_label_no_symbolic": (
                    diagnosis_predictions_no_symbolic[-1][1].label.value
                    if run_symbolic_ablation and diagnosis_predictions_no_symbolic
                    else None
                ),
            }
        )

    total = len(records)
    print("\n=== Evaluation Summary ===")
    print(f"Dataset split: {split}")
    print(f"Load success: {report.success}/{report.total}")
    print(f"Evaluated records: {total}")
    print(f"Parse success rate: {parse_success}/{total} ({(parse_success/total*100) if total else 0:.2f}%)")
    print(
        "Reference correctness: "
        f"{reference_correct}/{parse_success} ({(reference_correct/parse_success*100) if parse_success else 0:.2f}%)"
    )
    print(f"Spoiler-free rate: {spoiler_free}/{total} ({(spoiler_free/total*100) if total else 0:.2f}%)")
    print(f"Hint-alignment rate: {hint_alignment_ok}/{total} ({(hint_alignment_ok/total*100) if total else 0:.2f}%)")

    if label_map:
        diag_report = evaluate_diagnoses(diagnosis_predictions, label_map)
        print(
            f"Diagnosis accuracy (labeled subset): {diag_report.correct}/{diag_report.labeled_count} "
            f"({diag_report.accuracy*100:.2f}%)"
        )

        calib = compute_confidence_calibration(
            diagnosis_predictions,
            label_map,
            num_bins=calibration_bins,
        )
        print(
            f"Diagnosis calibration: ECE={calib.ece:.4f}, MCE={calib.mce:.4f}, "
            f"bins={calib.num_bins}, labeled={calib.labeled_count}"
        )

        if run_symbolic_ablation and diagnosis_predictions_no_symbolic:
            ablation = compare_symbolic_ablation(
                with_symbolic=diagnosis_predictions,
                without_symbolic=diagnosis_predictions_no_symbolic,
                ground_truth=label_map,
            )
            print(
                "Symbolic ablation (diagnosis): "
                f"with={ablation.with_symbolic_accuracy*100:.2f}%, "
                f"without={ablation.without_symbolic_accuracy*100:.2f}%, "
                f"delta={ablation.delta_accuracy*100:.2f}pp, "
                f"changed={ablation.changed_predictions}, "
                f"improved={ablation.improved_cases}, degraded={ablation.degraded_cases}"
            )

    print("Verification status distribution:")
    for status, count in verification_counter.most_common():
        print(f"  - {status}: {count}")

    print("Diagnosis label distribution:")
    for label, count in diagnosis_counter.most_common():
        print(f"  - {label}: {count}")

    if audit_output:
        write_audit_jsonl(audit_output, audit_rows)
        print(f"Audit rows written to: {audit_output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run baseline evaluation on GSM8K")
    parser.add_argument("--split", default="test", choices=["train", "test"])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--audit-labels", type=str, default=None, help="Path to gold diagnosis labels (.json/.jsonl/.csv)")
    parser.add_argument("--audit-output", type=str, default=None, help="Path to write evaluation audit rows (.jsonl)")
    parser.add_argument("--calibration-bins", type=int, default=5, help="Number of confidence bins for calibration metrics")
    parser.add_argument("--ablation-no-symbolic", action="store_true", help="Run diagnosis again without symbolic evidence for ablation")
    args = parser.parse_args()
    evaluate(
        split=args.split,
        limit=args.limit,
        audit_labels=args.audit_labels,
        audit_output=args.audit_output,
        calibration_bins=args.calibration_bins,
        run_symbolic_ablation=args.ablation_no_symbolic,
    )


if __name__ == "__main__":
    main()
