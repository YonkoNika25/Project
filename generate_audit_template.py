"""Generate a CSV audit template from a benchmark draft JSONL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.eval import build_audit_review_template, write_audit_review_csv
from src.models import BenchmarkSample


def load_benchmark_samples(path: str) -> list[BenchmarkSample]:
    rows = []
    p = Path(path)
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(BenchmarkSample.model_validate(json.loads(line)))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CSV audit template from benchmark draft JSONL")
    parser.add_argument("--benchmark", default="data/benchmark/benchmark_draft_v2.jsonl")
    parser.add_argument("--output", default="data/benchmark/benchmark_audit_template.csv")
    args = parser.parse_args()

    samples = load_benchmark_samples(args.benchmark)
    template = build_audit_review_template(samples)
    write_audit_review_csv(args.output, template)

    print(f"Generated audit template: {args.output}")
    print(f"Review rows: {len(template)}")


if __name__ == "__main__":
    main()
