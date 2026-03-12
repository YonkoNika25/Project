"""GSM8K dataset loader: loads and normalises raw GSM8K data into ProblemRecord schemas."""
import logging
from dataclasses import dataclass
from typing import List, Optional

from src.models import ProblemRecord
from src.dataset.answer_parser import parse_gsm8k_answer

logger = logging.getLogger(__name__)


@dataclass
class LoadReport:
    """Summary of a dataset load operation."""
    total: int
    success: int
    failed: int
    failed_ids: List[str]


def load_gsm8k_from_records(
    records: List[dict],
    split: str = "train",
    source: str = "gsm8k",
) -> tuple[List[ProblemRecord], LoadReport]:
    """Load GSM8K records into validated ProblemRecord objects.

    Args:
        records: List of raw dicts with ``question`` and ``answer`` keys.
        split: Dataset split name (train/test).
        source: Dataset source identifier.

    Returns:
        Tuple of (list of valid ProblemRecords, LoadReport).
    """
    results: List[ProblemRecord] = []
    failed_ids: List[str] = []
    success_count = 0

    for idx, raw in enumerate(records):
        record_id = f"{source}_{split}_{idx:05d}"

        question = raw.get("question", "")
        answer_text = raw.get("answer", "")

        if not question:
            logger.warning("Record %s: empty question field — skipping", record_id)
            failed_ids.append(record_id)
            continue

        gold_value, parsed_ok = parse_gsm8k_answer(answer_text)

        if not parsed_ok or gold_value is None:
            logger.warning(
                "Record %s: failed to parse gold answer from '%s'",
                record_id,
                answer_text[:80],
            )
            failed_ids.append(record_id)
            continue

        try:
            problem = ProblemRecord(
                id=record_id,
                problem=question,
                gold_answer_text=answer_text,
                gold_answer_value=gold_value,
                metadata={"source": source, "split": split, "index": idx},
            )
            results.append(problem)
            success_count += 1
            logger.debug("Record %s: loaded successfully (answer=%s)", record_id, gold_value)
        except Exception as exc:
            logger.error("Record %s: schema validation failed — %s", record_id, exc)
            failed_ids.append(record_id)

    report = LoadReport(
        total=len(records),
        success=success_count,
        failed=len(failed_ids),
        failed_ids=failed_ids,
    )

    logger.info(
        "GSM8K load complete: %d/%d success, %d failed",
        report.success,
        report.total,
        report.failed,
    )

    return results, report


def load_gsm8k_from_huggingface(
    split: str = "train",
    max_records: Optional[int] = None,
) -> tuple[List[ProblemRecord], LoadReport]:
    """Load GSM8K directly from HuggingFace datasets library.

    Requires ``pip install datasets``.

    Args:
        split: 'train' or 'test'.

    Returns:
        Tuple of (list of valid ProblemRecords, LoadReport).
    """
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        raise ImportError(
            "The 'datasets' library is required for HuggingFace loading. "
            "Install with: pip install datasets"
        )

    ds = load_dataset("openai/gsm8k", "main", split=split)
    if max_records is not None and max_records >= 0:
        ds = ds.select(range(min(max_records, len(ds))))
    raw_records = [{"question": r["question"], "answer": r["answer"]} for r in ds]
    return load_gsm8k_from_records(raw_records, split=split)
