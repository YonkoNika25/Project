"""I/O helpers for evaluation labels and audit logs."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List

from src.models import AuditDecision, AuditReviewRecord, BenchmarkSample, DiagnosisLabel, ErrorLocalization


def _parse_label(raw: str) -> DiagnosisLabel:
    try:
        return DiagnosisLabel(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid diagnosis label '{raw}'") from exc


def load_label_map(path: str) -> Dict[str, DiagnosisLabel]:
    """Load gold diagnosis labels from .json/.jsonl/.csv file.

    Supported layouts:
    - json dict: {"problem_id": "arithmetic_error", ...}
    - json list/jsonl rows: {"id"|"problem_id": "...", "label"|"diagnosis_label": "..."}
    - csv with columns: id/problem_id and label/diagnosis_label
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Label file not found: {path}")

    suffix = p.suffix.lower()
    if suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): _parse_label(str(v)) for k, v in data.items()}
        if isinstance(data, list):
            return _from_row_iter(data)
        raise ValueError("Unsupported JSON format for labels")

    if suffix == ".jsonl":
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return _from_row_iter(rows)

    if suffix == ".csv":
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return _from_row_iter(reader)

    raise ValueError("Unsupported label file format (use .json, .jsonl, .csv)")


def _from_row_iter(rows: Iterable[dict]) -> Dict[str, DiagnosisLabel]:
    label_map: Dict[str, DiagnosisLabel] = {}
    for row in rows:
        pid = str(row.get("id") or row.get("problem_id") or "").strip()
        label_raw = str(row.get("label") or row.get("diagnosis_label") or "").strip()
        if not pid or not label_raw:
            continue
        label_map[pid] = _parse_label(label_raw)
    return label_map


def _write_jsonl(path: str, entries: Iterable[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in entries:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_audit_jsonl(path: str, entries: Iterable[dict]) -> None:
    """Write audit records to JSONL file."""
    _write_jsonl(path, entries)


def write_benchmark_jsonl(path: str, entries: Iterable[dict]) -> None:
    """Write benchmark sample drafts to JSONL file."""
    _write_jsonl(path, entries)


def build_audit_review_template(samples: Iterable[BenchmarkSample]) -> List[AuditReviewRecord]:
    """Create default review records for a benchmark draft."""
    return [
        AuditReviewRecord(
            sample_id=sample.sample_id,
            decision=AuditDecision.KEEP,
            reviewer=None,
            notes="",
            updated_primary_label=sample.gold_diagnosis.primary_label,
            updated_localization=sample.gold_diagnosis.localization,
            updated_rationale=sample.gold_diagnosis.rationale,
            updated_split=sample.split,
            approved_for_subset=False,
        )
        for sample in samples
    ]


def write_audit_review_csv(path: str, entries: Iterable[AuditReviewRecord]) -> None:
    """Write review decisions to CSV for manual editing."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sample_id",
        "decision",
        "reviewer",
        "notes",
        "updated_primary_label",
        "updated_localization",
        "updated_rationale",
        "updated_split",
        "approved_for_subset",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            row = entry.model_dump(mode="json")
            writer.writerow(row)


def load_audit_review_csv(path: str) -> List[AuditReviewRecord]:
    """Load manual audit decisions from CSV."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Audit review CSV not found: {path}")

    records: List[AuditReviewRecord] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sample_id = str(row.get("sample_id") or "").strip()
            if not sample_id:
                continue

            decision_raw = str(row.get("decision") or AuditDecision.KEEP.value).strip() or AuditDecision.KEEP.value
            decision = AuditDecision(decision_raw)

            label_raw = str(row.get("updated_primary_label") or "").strip()
            localization_raw = str(row.get("updated_localization") or "").strip()
            approved_raw = str(row.get("approved_for_subset") or "").strip().lower()

            records.append(
                AuditReviewRecord(
                    sample_id=sample_id,
                    decision=decision,
                    reviewer=str(row.get("reviewer") or "").strip() or None,
                    notes=str(row.get("notes") or "").strip(),
                    updated_primary_label=DiagnosisLabel(label_raw) if label_raw else None,
                    updated_localization=ErrorLocalization(localization_raw) if localization_raw else None,
                    updated_rationale=str(row.get("updated_rationale") or "").strip() or None,
                    updated_split=str(row.get("updated_split") or "").strip() or None,
                    approved_for_subset=approved_raw in {"1", "true", "yes", "y"},
                )
            )

    return records
