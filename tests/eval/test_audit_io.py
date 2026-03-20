import json
from pathlib import Path

import pytest

from src.eval.audit_io import (
    build_audit_review_template,
    load_audit_review_csv,
    load_label_map,
    write_audit_jsonl,
    write_audit_review_csv,
    write_benchmark_jsonl,
)
from src.models import (
    AuditDecision,
    BenchmarkMetadata,
    BenchmarkProblem,
    BenchmarkSample,
    DiagnosisLabel,
    ErrorLocalization,
    GoldDiagnosisAnnotation,
    GoldReferenceAnnotation,
    StudentCase,
)


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


def test_write_benchmark_jsonl(tmp_path: Path):
    p = tmp_path / "benchmark" / "rows.jsonl"
    rows = [{"sample_id": "s1", "split": "train_build"}]
    write_benchmark_jsonl(str(p), rows)

    content = p.read_text(encoding="utf-8").strip()
    assert json.loads(content)["sample_id"] == "s1"


def test_build_and_load_audit_review_csv(tmp_path: Path):
    sample = BenchmarkSample(
        sample_id="s1",
        split="dev_audit",
        source_dataset="gsm8k",
        source_problem_id="gsm8k_train_00001",
        source_type="synthetic_draft",
        problem=BenchmarkProblem(text="How many apples are left?"),
        gold_reference=GoldReferenceAnnotation(final_answer=7.0, solution_text="#### 7"),
        student_case=StudentCase(student_answer_raw="5", student_answer_value=5.0, error_generation_method="synthetic"),
        gold_diagnosis=GoldDiagnosisAnnotation(
            primary_label=DiagnosisLabel.TARGET_MISUNDERSTANDING,
            localization=ErrorLocalization.TARGET_SELECTION,
            confidence=0.8,
            rationale="Student picked a non-target quantity.",
        ),
        metadata=BenchmarkMetadata(created_by="generator"),
    )

    template = build_audit_review_template([sample])
    assert template[0].decision == AuditDecision.KEEP
    assert template[0].updated_primary_label == DiagnosisLabel.TARGET_MISUNDERSTANDING

    p = tmp_path / "audit" / "review.csv"
    write_audit_review_csv(str(p), template)

    loaded = load_audit_review_csv(str(p))
    assert loaded[0].sample_id == "s1"
    assert loaded[0].decision == AuditDecision.KEEP
    assert loaded[0].updated_localization == ErrorLocalization.TARGET_SELECTION
