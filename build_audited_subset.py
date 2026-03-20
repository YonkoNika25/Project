"""Build an audited benchmark subset from draft JSONL and manual review CSV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.eval import load_audit_review_csv, write_benchmark_jsonl
from src.models import AuditDecision, BenchmarkSample


def load_benchmark_samples(path: str) -> list[BenchmarkSample]:
    rows = []
    p = Path(path)
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(BenchmarkSample.model_validate(json.loads(line)))
    return rows


def apply_review(sample: BenchmarkSample, review) -> BenchmarkSample | None:
    if review.decision == AuditDecision.DROP:
        return None

    data = sample.model_dump(mode="python")

    if review.updated_split:
        data["split"] = review.updated_split

    if review.updated_primary_label is not None:
        data["gold_diagnosis"]["primary_label"] = review.updated_primary_label
    if review.updated_localization is not None:
        data["gold_diagnosis"]["localization"] = review.updated_localization
    if review.updated_rationale:
        data["gold_diagnosis"]["rationale"] = review.updated_rationale

    data["gold_diagnosis"]["review_status"] = "approved" if review.approved_for_subset else "reviewed"
    notes = review.notes.strip()
    if notes:
        data["gold_diagnosis"]["review_notes"] = notes
        data["metadata"]["notes"] = notes

    reviewers = list(data["metadata"].get("reviewers", []))
    if review.reviewer and review.reviewer not in reviewers:
        reviewers.append(review.reviewer)
    data["metadata"]["reviewers"] = reviewers
    data["metadata"]["review_status"] = "approved" if review.approved_for_subset else "reviewed"
    data["source_type"] = "audited_subset"

    return BenchmarkSample.model_validate(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build audited subset from benchmark draft and review CSV")
    parser.add_argument("--benchmark", default="data/benchmark/benchmark_draft_v2.jsonl")
    parser.add_argument("--review", default="data/benchmark/benchmark_audit_template.csv")
    parser.add_argument("--output", default="data/benchmark/benchmark_audited_subset.jsonl")
    parser.add_argument("--approved-only", action="store_true", help="Only keep rows marked approved_for_subset=true")
    args = parser.parse_args()

    samples = load_benchmark_samples(args.benchmark)
    reviews = {review.sample_id: review for review in load_audit_review_csv(args.review)}

    audited: list[BenchmarkSample] = []
    missing_reviews = []
    for sample in samples:
        review = reviews.get(sample.sample_id)
        if review is None:
            missing_reviews.append(sample.sample_id)
            continue
        if args.approved_only and not review.approved_for_subset:
            continue
        updated = apply_review(sample, review)
        if updated is not None:
            audited.append(updated)

    write_benchmark_jsonl(args.output, [sample.model_dump(mode="json") for sample in audited])

    print(f"Built audited subset: {args.output}")
    print(f"Samples kept: {len(audited)}")
    print(f"Samples without review row: {len(missing_reviews)}")


if __name__ == "__main__":
    main()
