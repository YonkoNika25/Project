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
from src.hint.controller import HintController
from src.models import SolverResponse, SolverStatus, DiagnosisLabel
from src.solver.reference_parser import parse_solver_response, ParseStatus
from src.utils.llm_client import hf_llm_adapter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def evaluate(split: str, limit: int) -> None:
    records, report = load_gsm8k_from_huggingface(split=split)
    records = records[:limit]

    parse_success = 0
    reference_correct = 0
    spoiler_free = 0
    diagnosis_counter: Counter[str] = Counter()

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
            model_name="Qwen/Qwen2.5-Math-7B-Instruct",
            latency_ms=0.0,
            attempt_count=1,
        )
        parse_result = parse_solver_response(solver_response)

        if parse_result.status != ParseStatus.SUCCESS or parse_result.reference is None:
            diagnosis_counter[DiagnosisLabel.UNKNOWN_ERROR.value] += 1
            logger.warning("[%d/%d] parse failed: %s", idx, len(records), parse_result.status.value)
            logger.warning("RAW OUTPUT:\n%s\n---", raw_solve)
            continue

        parse_success += 1
        ref_sol = parse_result.reference
        if abs(ref_sol.final_answer - rec.gold_answer_value) < 1e-9:
            reference_correct += 1

        # Synthetic student answer to exercise diagnosis + hint pipeline
        student_answer = f"I think the answer is {ref_sol.final_answer - 1}."
        check_res = check_answer(student_answer, ref_sol.final_answer)
        diag_res = diagnose(
            problem_text=rec.problem,
            reference_solution_text=ref_sol.solution_text,
            reference_answer=ref_sol.final_answer,
            student_raw=student_answer,
            check_result=check_res,
            llm_callable=hf_llm_adapter,
        )
        diagnosis_counter[diag_res.label.value] += 1

        hint_res = hint_controller.get_hint(
            problem_text=rec.problem,
            reference_solution_text=ref_sol.solution_text,
            reference_answer=ref_sol.final_answer,
            student_raw=student_answer,
            diagnosis=diag_res,
        )
        if not hint_res.fallback_used:
            spoiler_free += 1

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
    print("Diagnosis label distribution:")
    for label, count in diagnosis_counter.most_common():
        print(f"  - {label}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run baseline evaluation on GSM8K")
    parser.add_argument("--split", default="test", choices=["train", "test"])
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    evaluate(split=args.split, limit=args.limit)


if __name__ == "__main__":
    main()
