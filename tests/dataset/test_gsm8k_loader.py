import logging
import pytest
from src.dataset.gsm8k_loader import load_gsm8k_from_records, LoadReport
from src.models import ProblemRecord


SAMPLE_RECORDS = [
    {"question": "Juan has 5 apples. He buys 3 more. How many?", "answer": "5+3=8\n#### 8"},
    {"question": "A farmer has 10 cows and sells 4. How many remain?", "answer": "10-4=6\n#### 6"},
    {"question": "What is 7 times 3?", "answer": "7*3=21\n#### 21"},
]


class TestLoadGsm8kFromRecords:
    def test_all_valid_records(self):
        results, report = load_gsm8k_from_records(SAMPLE_RECORDS, split="test")
        assert len(results) == 3
        assert report.total == 3
        assert report.success == 3
        assert report.failed == 0
        assert report.failed_ids == []

    def test_records_are_problem_records(self):
        results, _ = load_gsm8k_from_records(SAMPLE_RECORDS)
        for r in results:
            assert isinstance(r, ProblemRecord)

    def test_record_id_format(self):
        results, _ = load_gsm8k_from_records(SAMPLE_RECORDS, split="train")
        assert results[0].id == "gsm8k_train_00000"
        assert results[1].id == "gsm8k_train_00001"
        assert results[2].id == "gsm8k_train_00002"

    def test_metadata_populated(self):
        results, _ = load_gsm8k_from_records(SAMPLE_RECORDS, split="test")
        assert results[0].metadata["source"] == "gsm8k"
        assert results[0].metadata["split"] == "test"
        assert results[0].metadata["index"] == 0

    def test_gold_answer_extracted(self):
        results, _ = load_gsm8k_from_records(SAMPLE_RECORDS)
        assert results[0].gold_answer_value == 8.0
        assert results[1].gold_answer_value == 6.0
        assert results[2].gold_answer_value == 21.0

    def test_malformed_answer_skipped(self):
        records = [
            {"question": "Good question?", "answer": "#### 5"},
            {"question": "Bad question?", "answer": "No hash pattern here"},
        ]
        results, report = load_gsm8k_from_records(records)
        assert len(results) == 1
        assert report.success == 1
        assert report.failed == 1
        assert "gsm8k_train_00001" in report.failed_ids

    def test_empty_question_skipped(self):
        records = [
            {"question": "", "answer": "#### 5"},
            {"question": "Valid?", "answer": "#### 10"},
        ]
        results, report = load_gsm8k_from_records(records)
        assert len(results) == 1
        assert report.failed == 1

    def test_empty_records_list(self):
        results, report = load_gsm8k_from_records([])
        assert len(results) == 0
        assert report.total == 0
        assert report.success == 0
        assert report.failed == 0

    def test_failure_logging(self, caplog):
        records = [{"question": "Q?", "answer": "No answer marker"}]
        with caplog.at_level(logging.WARNING):
            _, report = load_gsm8k_from_records(records)
        assert report.failed == 1
        assert any("failed to parse" in msg for msg in caplog.messages)

    def test_success_logging(self, caplog):
        with caplog.at_level(logging.INFO):
            _, report = load_gsm8k_from_records(SAMPLE_RECORDS)
        assert any("load complete" in msg for msg in caplog.messages)
