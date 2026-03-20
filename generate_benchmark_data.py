"""Generate first-round benchmark draft data from GSM8K."""
from __future__ import annotations

import argparse
import json
from collections import Counter

from src.dataset.gsm8k_loader import load_gsm8k_from_huggingface
from src.eval import generate_benchmark_bundle, write_benchmark_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate first-round benchmark draft data from GSM8K")
    parser.add_argument("--split", default="train", choices=["train", "test"])
    parser.add_argument("--input-limit", type=int, default=200, help="How many raw GSM8K problems to scan")
    parser.add_argument("--base-limit", type=int, default=30, help="How many base problems to keep")
    parser.add_argument(
        "--cases-per-problem",
        type=int,
        default=3,
        help="Maximum benchmark cases to generate from each base problem",
    )
    parser.add_argument(
        "--output",
        default="data/benchmark/benchmark_draft.jsonl",
        help="Where to write the benchmark draft JSONL",
    )
    parser.add_argument(
        "--scores-output",
        default="data/benchmark/benchmark_selection_scores.json",
        help="Where to write problem selection scores",
    )
    args = parser.parse_args()

    records, report = load_gsm8k_from_huggingface(split=args.split, max_records=args.input_limit)
    bundle = generate_benchmark_bundle(
        records,
        base_problem_limit=args.base_limit,
        max_cases_per_problem=args.cases_per_problem,
    )

    write_benchmark_jsonl(
        args.output,
        [sample.model_dump(mode="json") for sample in bundle.samples],
    )

    with open(args.scores_output, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "problem_id": score.problem_id,
                    "score": score.score,
                    "reasons": score.reasons,
                }
                for score in bundle.selection_scores
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )

    split_counts = Counter(sample.split for sample in bundle.samples)
    label_counts = Counter(sample.gold_diagnosis.primary_label.value for sample in bundle.samples)

    print("\n=== Benchmark Draft Generation Summary ===")
    print(f"Raw load success: {report.success}/{report.total}")
    print(f"Selected base problems: {len(bundle.selected_problems)}")
    print(f"Generated benchmark samples: {len(bundle.samples)}")
    print(f"Benchmark output: {args.output}")
    print(f"Selection scores output: {args.scores_output}")
    print("Split distribution:")
    for split, count in split_counts.items():
        print(f"  - {split}: {count}")
    print("Diagnosis label distribution:")
    for label, count in label_counts.items():
        print(f"  - {label}: {count}")


if __name__ == "__main__":
    main()
