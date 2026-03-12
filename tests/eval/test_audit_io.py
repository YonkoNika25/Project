import json
from pathlib import Path

import pytest

from src.eval.audit_io import load_label_map, write_audit_jsonl
from src.models import DiagnosisLabel


def test_load_label_map_from_json_dict(tmp_path: Path):
    p = tmp_path / "labels.json"
    p.write_text(json.dumps({"q1": "arithmetic_error", "q2": "unknown_error"}), encoding="utf-8")

    out = load_label_map(str(p))
    assert out["q1"] == DiagnosisLabel.ARITHMETIC_ERROR
    assert out["q2"] == DiagnosisLabel.UNKNOWN_ERROR


def test_load_label_map_from_jsonl(tmp_path: Path):
    p = tmp_path / "labels.jsonl"
    p.write_text(
        json.dumps({"id": "q1", "label": "quantity_relation_error"}) + "\n" +
        json.dumps({"problem_id": "q2", "diagnosis_label": "target_misunderstanding"}) + "\n",
        encoding="utf-8",
    )

    out = load_label_map(str(p))
    assert out["q1"] == DiagnosisLabel.QUANTITY_RELATION_ERROR
    assert out["q2"] == DiagnosisLabel.TARGET_MISUNDERSTANDING


def test_load_label_map_from_csv(tmp_path: Path):
    p = tmp_path / "labels.csv"
    p.write_text("problem_id,diagnosis_label\nq1,arithmetic_error\n", encoding="utf-8")

    out = load_label_map(str(p))
    assert out["q1"] == DiagnosisLabel.ARITHMETIC_ERROR


def test_load_label_map_invalid_label_raises(tmp_path: Path):
    p = tmp_path / "labels.json"
    p.write_text(json.dumps({"q1": "not_a_label"}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_label_map(str(p))


def test_write_audit_jsonl(tmp_path: Path):
    p = tmp_path / "audit" / "rows.jsonl"
    rows = [{"problem_id": "q1", "diagnosis_label": "unknown_error"}]
    write_audit_jsonl(str(p), rows)

    content = p.read_text(encoding="utf-8").strip()
    assert json.loads(content)["problem_id"] == "q1"
