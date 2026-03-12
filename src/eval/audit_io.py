"""I/O helpers for evaluation labels and audit logs."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable

from src.models import DiagnosisLabel


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


def write_audit_jsonl(path: str, entries: Iterable[dict]) -> None:
    """Write audit records to JSONL file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in entries:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
