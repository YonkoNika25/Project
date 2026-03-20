"""Run evaluation on curated benchmark samples."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from src.eval import evaluate_benchmark_samples, load_benchmark_samples, write_audit_jsonl
from src.utils.llm_client import openrouter_llm_adapter


def _summary_to_dict(summary) -> dict:
    return {
        "total_samples": summary.total_samples,
        "split_distribution": summary.split_distribution,
        "diagnosis": {
            "accuracy": summary.diagnosis_report.accuracy,
            "total": summary.diagnosis_report.total,
            "labeled_count": summary.diagnosis_report.labeled_count,
            "correct": summary.diagnosis_report.correct,
            "incorrect": summary.diagnosis_report.incorrect,
            "label_distribution": summary.diagnosis_report.label_distribution,
        },
        "localization": {
            "accuracy": summary.localization_report.accuracy,
            "total": summary.localization_report.total,
            "correct": summary.localization_report.correct,
        },
        "calibration": {
            "labeled_count": summary.calibration_report.labeled_count,
            "num_bins": summary.calibration_report.num_bins,
            "ece": summary.calibration_report.ece,
            "mce": summary.calibration_report.mce,
            "bins": [
                {
                    "low": bin_.low,
                    "high": bin_.high,
                    "count": bin_.count,
                    "accuracy": bin_.accuracy,
                    "avg_confidence": bin_.avg_confidence,
                    "gap": bin_.gap,
                }
                for bin_ in summary.calibration_report.bins
            ],
        },
        "ablation": {
            "labeled_count": summary.ablation_report.labeled_count,
            "with_symbolic_accuracy": summary.ablation_report.with_symbolic_accuracy,
            "without_symbolic_accuracy": summary.ablation_report.without_symbolic_accuracy,
            "delta_accuracy": summary.ablation_report.delta_accuracy,
            "changed_predictions": summary.ablation_report.changed_predictions,
            "improved_cases": summary.ablation_report.improved_cases,
            "degraded_cases": summary.ablation_report.degraded_cases,
        },
        "hints": {
            "spoiler_free_rate": summary.spoiler_free_rate,
            "hint_alignment_rate": summary.hint_alignment_rate,
            "hint_fallback_rate": summary.hint_fallback_rate,
        },
        "verification_status_distribution": summary.verification_status_distribution,
        "confusion_matrix": summary.confusion_matrix.matrix,
    }


def _print_summary(summary) -> None:
    print("\n=== Benchmark Evaluation Summary ===")
    print(f"Total samples: {summary.total_samples}")
    print(f"Split distribution: {summary.split_distribution}")
    print(
        "Diagnosis accuracy: "
        f"{summary.diagnosis_report.correct}/{summary.diagnosis_report.labeled_count} "
        f"({summary.diagnosis_report.accuracy * 100:.2f}%)"
    )
    print(
        "Localization accuracy: "
        f"{summary.localization_report.correct}/{summary.localization_report.total} "
        f"({summary.localization_report.accuracy * 100:.2f}%)"
    )
    print(
        "Calibration: "
        f"ECE={summary.calibration_report.ece:.4f}, "
        f"MCE={summary.calibration_report.mce:.4f}"
    )
    print(
        "Ablation (with symbolic vs without symbolic): "
        f"{summary.ablation_report.with_symbolic_accuracy * 100:.2f}% vs "
        f"{summary.ablation_report.without_symbolic_accuracy * 100:.2f}% "
        f"(delta {summary.ablation_report.delta_accuracy * 100:+.2f}%)"
    )
    print(
        "Hint metrics: "
        f"spoiler-free={summary.spoiler_free_rate * 100:.2f}%, "
        f"alignment={summary.hint_alignment_rate * 100:.2f}%, "
        f"fallback={summary.hint_fallback_rate * 100:.2f}%"
    )
    print(f"Verification status distribution: {summary.verification_status_distribution}")
    print("Diagnosis confusion matrix:")
    for gold_label, row in summary.confusion_matrix.matrix.items():
        print(f"  {gold_label}: {row}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate curated diagnosis/hint benchmark")
    parser.add_argument(
        "--benchmark",
        default="data/benchmark/benchmark_draft_v2.jsonl",
        help="Path to benchmark JSONL",
    )
    parser.add_argument(
        "--audit-output",
        default="data/benchmark/benchmark_eval_audit.jsonl",
        help="Where to write per-sample audit JSONL",
    )
    parser.add_argument(
        "--summary-output",
        default="data/benchmark/benchmark_eval_summary.json",
        help="Where to write aggregate summary JSON",
    )
    parser.add_argument(
        "--split",
        default=None,
        choices=["train_build", "dev_audit", "test_paper"],
        help="Optional split filter",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of samples")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Enable LLM fallback for diagnosis/hint generation",
    )
    parser.add_argument(
        "--no-hints",
        action="store_true",
        help="Skip hint generation and hint metrics",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show warning-level logs from diagnosis/hint pipeline",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.verbose else logging.ERROR,
        format="%(levelname)s: %(message)s",
    )

    samples = load_benchmark_samples(args.benchmark)
    if args.split is not None:
        samples = [sample for sample in samples if sample.split == args.split]
    if args.limit is not None:
        samples = samples[: args.limit]

    llm_callable = openrouter_llm_adapter if args.with_llm else None
    summary, audit_entries = evaluate_benchmark_samples(
        samples,
        llm_callable=llm_callable,
        run_hints=not args.no_hints,
    )

    write_audit_jsonl(args.audit_output, audit_entries)

    summary_payload = _summary_to_dict(summary)
    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _print_summary(summary)
    print(f"\nAudit log written to: {args.audit_output}")
    print(f"Summary written to: {args.summary_output}")


if __name__ == "__main__":
    main()
