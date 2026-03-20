"""Run robustness evaluation on stressed benchmark variants."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from src.eval import evaluate_benchmark_samples, generate_stress_variants, load_benchmark_samples, write_audit_jsonl
from src.utils.llm_client import openrouter_llm_adapter


def _summary_payload(summary) -> dict:
    return {
        "total_samples": summary.total_samples,
        "diagnosis_accuracy": summary.diagnosis_report.accuracy,
        "localization_accuracy": summary.localization_report.accuracy,
        "ece": summary.calibration_report.ece,
        "mce": summary.calibration_report.mce,
        "with_symbolic_accuracy": summary.ablation_report.with_symbolic_accuracy,
        "without_symbolic_accuracy": summary.ablation_report.without_symbolic_accuracy,
        "delta_accuracy": summary.ablation_report.delta_accuracy,
        "hint_alignment_rate": summary.hint_alignment_rate,
        "hint_fallback_rate": summary.hint_fallback_rate,
        "verification_status_distribution": summary.verification_status_distribution,
    }


def _print_summary(name: str, summary) -> None:
    print(f"\n=== {name} ===")
    print(
        f"Diagnosis accuracy: {summary.diagnosis_report.correct}/{summary.diagnosis_report.labeled_count} "
        f"({summary.diagnosis_report.accuracy * 100:.2f}%)"
    )
    print(
        f"Localization accuracy: {summary.localization_report.correct}/{summary.localization_report.total} "
        f"({summary.localization_report.accuracy * 100:.2f}%)"
    )
    print(
        f"Calibration: ECE={summary.calibration_report.ece:.4f}, "
        f"MCE={summary.calibration_report.mce:.4f}"
    )
    print(
        f"Ablation: with symbolic={summary.ablation_report.with_symbolic_accuracy * 100:.2f}%, "
        f"without symbolic={summary.ablation_report.without_symbolic_accuracy * 100:.2f}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run stress evaluation on benchmark variants")
    parser.add_argument(
        "--benchmark",
        default="data/benchmark/benchmark_draft_v2.jsonl",
        help="Path to benchmark JSONL",
    )
    parser.add_argument(
        "--summary-output",
        default="data/benchmark/benchmark_stress_summary.json",
        help="Where to write combined summary JSON",
    )
    parser.add_argument(
        "--audit-output",
        default="data/benchmark/benchmark_stress_audit.jsonl",
        help="Where to write stressed per-sample audit JSONL",
    )
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
    stress_bundle = generate_stress_variants(samples)
    llm_callable = openrouter_llm_adapter if args.with_llm else None

    base_summary, _ = evaluate_benchmark_samples(
        stress_bundle.original_samples,
        llm_callable=llm_callable,
        run_hints=not args.no_hints,
    )
    stress_summary, stress_audit = evaluate_benchmark_samples(
        stress_bundle.stressed_samples,
        llm_callable=llm_callable,
        run_hints=not args.no_hints,
    )

    variant_family_map = {
        case.sample.sample_id: {
            "variant_family": case.variant_family,
            "variant_name": case.variant_name,
        }
        for case in stress_bundle.variant_cases
    }
    for entry in stress_audit:
        entry.update(variant_family_map.get(entry["sample_id"], {}))

    write_audit_jsonl(args.audit_output, stress_audit)

    family_summaries = {}
    for family in sorted({case.variant_family for case in stress_bundle.variant_cases}):
        family_samples = [case.sample for case in stress_bundle.variant_cases if case.variant_family == family]
        family_summary, _ = evaluate_benchmark_samples(
            family_samples,
            llm_callable=llm_callable,
            run_hints=not args.no_hints,
        )
        family_summaries[family] = {
            "sample_count": len(family_samples),
            **_summary_payload(family_summary),
        }

    payload = {
        "variant_names": stress_bundle.variant_names,
        "base": _summary_payload(base_summary),
        "stress": _summary_payload(stress_summary),
        "stress_by_variant_family": family_summaries,
        "delta": {
            "diagnosis_accuracy": stress_summary.diagnosis_report.accuracy - base_summary.diagnosis_report.accuracy,
            "localization_accuracy": stress_summary.localization_report.accuracy - base_summary.localization_report.accuracy,
            "ece": stress_summary.calibration_report.ece - base_summary.calibration_report.ece,
            "hint_alignment_rate": stress_summary.hint_alignment_rate - base_summary.hint_alignment_rate,
        },
    }

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_summary("Base benchmark", base_summary)
    _print_summary("Stress benchmark", stress_summary)
    print(
        "\nDelta diagnosis accuracy: "
        f"{(stress_summary.diagnosis_report.accuracy - base_summary.diagnosis_report.accuracy) * 100:+.2f}%"
    )
    print("Variant-family diagnosis accuracy:")
    for family, family_payload in family_summaries.items():
        print(f"  - {family}: {family_payload['diagnosis_accuracy'] * 100:.2f}% ({family_payload['sample_count']} samples)")
    print(f"Stress audit written to: {args.audit_output}")
    print(f"Stress summary written to: {args.summary_output}")


if __name__ == "__main__":
    main()
