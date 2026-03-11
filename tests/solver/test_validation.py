import pytest
from src.models import ProblemRecord, ReferenceSolution
from src.solver.reference_parser import ParseResult, ParseStatus
from src.solver.validation import (
    validate_batch,
    ValidationReport,
    AuditEntry,
    MatchStatus,
)


def _problem(pid: str = "p_001", gold: float = 8.0) -> ProblemRecord:
    return ProblemRecord(
        id=pid, problem="Q?", gold_answer_text="#### 8", gold_answer_value=gold
    )


def _success_result(answer: float = 8.0, model: str = "test") -> ParseResult:
    ref = ReferenceSolution(
        final_answer=answer,
        solution_text="steps",
        confidence=1.0,
        schema_version="1.0",
        source=model,
    )
    return ParseResult(status=ParseStatus.SUCCESS, reference=ref)


def _parse_fail_result() -> ParseResult:
    return ParseResult(status=ParseStatus.NO_ANSWER_FOUND, error_message="No ####")


def _solver_fail_result() -> ParseResult:
    return ParseResult(status=ParseStatus.SOLVER_FAILED, error_message="Timeout")


class TestValidateBatch:
    def test_all_correct(self):
        pairs = [
            (_problem("p1", 8.0), _success_result(8.0)),
            (_problem("p2", 6.0), _success_result(6.0)),
        ]
        report = validate_batch(pairs)
        assert report.total == 2
        assert report.parsed_ok == 2
        assert report.match_count == 2
        assert report.mismatch_count == 0
        assert report.accuracy == 1.0
        assert len(report.audit_entries) == 0

    def test_one_mismatch(self):
        pairs = [
            (_problem("p1", 8.0), _success_result(8.0)),
            (_problem("p2", 6.0), _success_result(9.0)),  # wrong
        ]
        report = validate_batch(pairs)
        assert report.match_count == 1
        assert report.mismatch_count == 1
        assert report.accuracy == 0.5
        assert len(report.audit_entries) == 1
        assert report.audit_entries[0].status == MatchStatus.INCORRECT

    def test_parse_failure(self):
        pairs = [(_problem("p1"), _parse_fail_result())]
        report = validate_batch(pairs)
        assert report.parse_fail_count == 1
        assert report.parsed_ok == 0
        assert report.accuracy == 0.0
        assert report.audit_entries[0].status == MatchStatus.PARSE_FAILED

    def test_solver_failure(self):
        pairs = [(_problem("p1"), _solver_fail_result())]
        report = validate_batch(pairs)
        assert report.solver_fail_count == 1
        assert report.audit_entries[0].status == MatchStatus.SOLVER_FAILED

    def test_mixed_batch(self):
        pairs = [
            (_problem("p1", 8.0), _success_result(8.0)),   # correct
            (_problem("p2", 6.0), _success_result(99.0)),   # mismatch
            (_problem("p3", 5.0), _parse_fail_result()),     # parse fail
            (_problem("p4", 3.0), _solver_fail_result()),    # solver fail
        ]
        report = validate_batch(pairs)
        assert report.total == 4
        assert report.match_count == 1
        assert report.mismatch_count == 1
        assert report.parse_fail_count == 1
        assert report.solver_fail_count == 1
        assert report.parsed_ok == 2
        assert len(report.audit_entries) == 3  # mismatch + parse_fail + solver_fail

    def test_empty_batch(self):
        report = validate_batch([])
        assert report.total == 0
        assert report.accuracy == 0.0

    def test_audit_entry_detail(self):
        pairs = [(_problem("p1", 10.0), _success_result(20.0))]
        report = validate_batch(pairs)
        entry = report.audit_entries[0]
        assert entry.problem_id == "p1"
        assert entry.gold_answer == 10.0
        assert entry.generated_answer == 20.0
        assert "Expected 10.0, got 20.0" in entry.detail

    def test_accuracy_property(self):
        pairs = [
            (_problem("p1", 8.0), _success_result(8.0)),
            (_problem("p2", 6.0), _success_result(6.0)),
            (_problem("p3", 5.0), _success_result(99.0)),
        ]
        report = validate_batch(pairs)
        assert report.accuracy == pytest.approx(2 / 3)
