"""Batch validation and audit of reference solutions against gold answers."""
import logging
from dataclasses import dataclass, field
from typing import List
from enum import Enum

from src.models import ProblemRecord
from src.solver.reference_parser import ParseResult, ParseStatus

logger = logging.getLogger(__name__)


class MatchStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARSE_FAILED = "parse_failed"
    SOLVER_FAILED = "solver_failed"


@dataclass
class AuditEntry:
    """Single audit entry for a problem's validation result."""
    problem_id: str
    gold_answer: float
    generated_answer: float | None
    status: MatchStatus
    detail: str = ""


@dataclass
class ValidationReport:
    """Aggregate metrics from batch validation."""
    total: int = 0
    parsed_ok: int = 0
    match_count: int = 0
    mismatch_count: int = 0
    parse_fail_count: int = 0
    solver_fail_count: int = 0
    audit_entries: List[AuditEntry] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if self.parsed_ok == 0:
            return 0.0
        return self.match_count / self.parsed_ok


def validate_batch(
    pairs: List[tuple[ProblemRecord, ParseResult]],
) -> ValidationReport:
    """Validate a batch of (ProblemRecord, ParseResult) pairs.

    Compares each reference solution's final_answer against the gold answer.

    Args:
        pairs: List of (problem, parse_result) tuples.

    Returns:
        ValidationReport with metrics and audit entries.
    """
    report = ValidationReport(total=len(pairs))

    for problem, parse_result in pairs:
        if parse_result.status == ParseStatus.SOLVER_FAILED:
            report.solver_fail_count += 1
            report.audit_entries.append(AuditEntry(
                problem_id=problem.id,
                gold_answer=problem.gold_answer_value,
                generated_answer=None,
                status=MatchStatus.SOLVER_FAILED,
                detail=parse_result.error_message or "Solver failed",
            ))
            continue

        if parse_result.status == ParseStatus.NO_ANSWER_FOUND:
            report.parse_fail_count += 1
            report.audit_entries.append(AuditEntry(
                problem_id=problem.id,
                gold_answer=problem.gold_answer_value,
                generated_answer=None,
                status=MatchStatus.PARSE_FAILED,
                detail=parse_result.error_message or "No answer found",
            ))
            continue

        # Parse succeeded
        report.parsed_ok += 1
        ref = parse_result.reference
        generated = ref.final_answer

        if generated == problem.gold_answer_value:
            report.match_count += 1
            logger.debug("%s: CORRECT (gold=%s)", problem.id, problem.gold_answer_value)
        else:
            report.mismatch_count += 1
            report.audit_entries.append(AuditEntry(
                problem_id=problem.id,
                gold_answer=problem.gold_answer_value,
                generated_answer=generated,
                status=MatchStatus.INCORRECT,
                detail=f"Expected {problem.gold_answer_value}, got {generated}",
            ))
            logger.warning(
                "%s: MISMATCH gold=%s vs generated=%s",
                problem.id, problem.gold_answer_value, generated,
            )

    logger.info(
        "Validation complete: %d total, %d correct, %d mismatch, %d parse_fail, %d solver_fail",
        report.total, report.match_count, report.mismatch_count,
        report.parse_fail_count, report.solver_fail_count,
    )

    return report
