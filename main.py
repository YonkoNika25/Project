"""Demo runner for the end-to-end tutoring pipeline."""
from __future__ import annotations

import json
from typing import Any

from src.input_loader import (
    DEFAULT_PROBLEM_PATH,
    DEFAULT_STUDENT_ANSWER_PATH,
    load_problem_and_student_answer,
)
from src.llm import LLMClient, build_default_llm_client
from src.models import HintMode
from src.pipeline import run_tutoring_pipeline


# When True, the pipeline will try the configured OpenRouter model and fall back
# safely to deterministic logic if an LLM step fails.
USE_LLM = True

# Other options: HintMode.SCAFFOLDING, HintMode.PEDAGOGY_FOLLOWING
HINT_MODE = HintMode.NORMAL

_LLM_TASK_ORDER = (
    "problem_formalizer",
    "student_work_formalizer",
    "diagnosis",
    "hint_generator",
    "hint_repair",
)


class RecordingLLMClient:
    """Wrap an LLM client and keep every successful/failed generation for inspection."""

    def __init__(self, base_client: LLMClient):
        self._base_client = base_client
        self.records: list[dict[str, Any]] = []

    def generate_json(
        self,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        try:
            payload = self._base_client.generate_json(
                task_name=task_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            self.records.append(
                {
                    "task_name": task_name,
                    "status": "error",
                    "error": str(exc),
                }
            )
            raise

        self.records.append(
            {
                "task_name": task_name,
                "status": "success",
                "response": payload,
            }
        )
        return payload


def _print_header(title: str) -> None:
    line = "=" * 24
    print(f"\n{line} {title} {line}")


def _print_json(title: str, payload) -> None:
    _print_header(title)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _print_llm_responses(
    records: list[dict[str, Any]],
    llm_requested: bool,
    llm_available: bool,
) -> None:
    _print_header("LLM Responses")

    if not llm_requested:
        print("LLM disabled.")
        return

    if not llm_available:
        print("No configured LLM client was available, so the pipeline ran without LLM calls.")
        return

    if not records:
        print("No LLM calls were captured.")
        return

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record["task_name"]), []).append(record)

    for task_name in _LLM_TASK_ORDER:
        task_records = grouped.get(task_name, [])
        print(f"\n[{task_name}]")
        if not task_records:
            print("  No call captured.")
            continue

        for index, record in enumerate(task_records, start=1):
            print(f"  Call {index}: {record['status']}")
            if record["status"] == "success":
                print(
                    json.dumps(
                        record["response"],
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"  Error: {record['error']}")


def main() -> None:
    problem_text, student_answer = load_problem_and_student_answer()
    base_llm_client = build_default_llm_client() if USE_LLM else None
    recording_llm_client = RecordingLLMClient(base_llm_client) if base_llm_client is not None else None
    active_use_llm = USE_LLM and recording_llm_client is not None

    print("Tutoring Pipeline Demo")
    print(f"PROBLEM_PATH = {DEFAULT_PROBLEM_PATH}")
    print(f"STUDENT_ANSWER_PATH = {DEFAULT_STUDENT_ANSWER_PATH}")
    print(f"USE_LLM = {USE_LLM}")
    print(f"HINT_MODE = {HINT_MODE.value}")
    print(f"LLM client available = {base_llm_client is not None}")

    result = run_tutoring_pipeline(
        problem_text=problem_text,
        student_answer=student_answer,
        hint_mode=HINT_MODE,
        llm_client=recording_llm_client,
        use_llm=active_use_llm,
    )

    _print_json("Input", {"problem_text": problem_text, "student_answer": student_answer})
    _print_json("Problem", result.problem.model_dump(mode="json"))
    _print_json("Reference", result.reference.model_dump(mode="json"))
    _print_json("Student Work", result.student_work.model_dump(mode="json"))
    _print_json("Evidence", result.evidence.model_dump(mode="json"))
    _print_json("Diagnosis", result.diagnosis.model_dump(mode="json"))
    _print_json("Hint Plan", result.hint_plan.model_dump(mode="json"))
    _print_json("Hint Result", result.hint_result.model_dump(mode="json"))
    _print_llm_responses(
        recording_llm_client.records if recording_llm_client is not None else [],
        llm_requested=USE_LLM,
        llm_available=base_llm_client is not None,
    )

    _print_header("Summary")
    print(f"Reference final answer: {result.reference.final_answer:g}")
    print(f"Student normalized answer: {result.student_work.normalized_final_answer}")
    print(f"Diagnosis label: {result.diagnosis.diagnosis_label.value}")
    print(f"Hint text: {result.hint_result.hint_text}")
    print(f"Hint verified: {result.hint_result.verification_passed}")


if __name__ == "__main__":
    main()
