"""Load shared problem and student-answer text from local input files."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "input"
DEFAULT_PROBLEM_PATH = DEFAULT_INPUT_DIR / "problem.txt"
DEFAULT_STUDENT_ANSWER_PATH = DEFAULT_INPUT_DIR / "student_answer.txt"


def _read_non_empty_text(path: Path, label: str) -> str:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {label} file: {path}. Create the file and add content."
        )

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{label} file is empty: {path}")
    return text


def load_problem_text(path: Path = DEFAULT_PROBLEM_PATH) -> str:
    return _read_non_empty_text(path, "problem")


def load_problem_and_student_answer(
    problem_path: Path = DEFAULT_PROBLEM_PATH,
    student_answer_path: Path = DEFAULT_STUDENT_ANSWER_PATH,
) -> tuple[str, str]:
    return (
        _read_non_empty_text(problem_path, "problem"),
        _read_non_empty_text(student_answer_path, "student answer"),
    )
