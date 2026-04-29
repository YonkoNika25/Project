"""Standalone debugger for the hint generation pipeline."""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import requests

from src.diagnosis import build_diagnosis
from src.evidence import build_diagnosis_context, build_diagnosis_evidence
from src.formalizer import formalize_problem, formalize_student_work
from src.hint import build_hint_result
from src.llm import LLMClient, LLMGenerationError, OpenRouterLLMClient, build_default_llm_client
from src.models import HintMode
from src.pedagogy import build_pedagogy_artifacts
from src.runtime import build_canonical_reference


PROBLEM_TEXT = (
    "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount "
    "for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?"
)
STUDENT_ANSWER = "12 * 40 = 480\n12 - 10 = 2\n5% of 40 = 2\n2 * 2 = 4\n480 - 4 = 474\nAnswer is 474."
USE_LLM = True
HINT_MODE = HintMode.NORMAL
WRITE_OUTPUT_TO_FILE = True
OUTPUT_PATH = Path("debug_hint_output.txt")
RAW_LLM_OUTPUT_PATH = Path("debug_hint_llm_raw.json")


class _TeeStream:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


def _print_header(title: str) -> None:
    line = "=" * 20
    print(f"\n{line} {title} {line}")


def _print_json(title: str, payload: Any) -> None:
    _print_header(title)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


class RecordingLLMClient:
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
        if isinstance(self._base_client, OpenRouterLLMClient):
            return self._generate_json_openrouter(
                task_name=task_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

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
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "error": str(exc),
                }
            )
            raise

        self.records.append(
            {
                "task_name": task_name,
                "status": "success",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response": payload,
            }
        )
        return payload

    def _generate_json_openrouter(
        self,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        client = self._base_client
        headers = {
            "Authorization": f"Bearer {client.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": client.app_name,
        }
        request_payload = {
            "model": client.model_id,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        raw_text: str | None = None
        raw_json: dict[str, Any] | None = None
        try:
            response = requests.post(
                f"{client.base_url}/chat/completions",
                headers=headers,
                json=request_payload,
                timeout=client.timeout_seconds,
            )
            raw_text = response.text
            response.raise_for_status()
            raw_json = response.json()
            content = raw_json["choices"][0]["message"]["content"]
            parsed_payload = client._parse_json_content(content)
        except requests.RequestException as exc:
            self.records.append(
                {
                    "task_name": task_name,
                    "status": "error",
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "error": f"{task_name} request failed: {exc}",
                    "request_payload": request_payload,
                    "raw_response_text": raw_text,
                    "raw_response_json": raw_json,
                }
            )
            raise LLMGenerationError(f"{task_name} request failed: {exc}") from exc
        except Exception as exc:
            self.records.append(
                {
                    "task_name": task_name,
                    "status": "error",
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "error": str(exc),
                    "request_payload": request_payload,
                    "raw_response_text": raw_text,
                    "raw_response_json": raw_json,
                }
            )
            raise

        self.records.append(
            {
                "task_name": task_name,
                "status": "success",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "request_payload": request_payload,
                "raw_response_text": raw_text,
                "raw_response_json": raw_json,
                "response": parsed_payload,
            }
        )
        return parsed_payload


def _print_llm_attempts(records: list[dict[str, Any]], llm_requested: bool, llm_available: bool) -> None:
    _print_header("LLM Attempts")
    if not llm_requested:
        print("LLM disabled.")
        return
    if not llm_available:
        print("No configured LLM client was available.")
        return
    if not records:
        print("No LLM attempts were captured.")
        return
    for index, record in enumerate(records, start=1):
        print(f"\nAttempt {index}")
        print(f"Task: {record['task_name']}")
        print(f"Status: {record['status']}")
        system_prompt = record.get("system_prompt")
        user_prompt = record.get("user_prompt")
        if system_prompt:
            print("System prompt sent to model:")
            print(system_prompt)
        if user_prompt:
            print("User prompt sent to model:")
            print(user_prompt)
        if record["status"] == "success":
            print(json.dumps(record["response"], indent=2, ensure_ascii=False))
        else:
            print(f"Error: {record['error']}")


def main() -> list[dict[str, Any]]:
    print("Hint Debugger")
    print(f"USE_LLM = {USE_LLM}")
    print(f"HINT_MODE = {HINT_MODE.value}")

    problem = formalize_problem(PROBLEM_TEXT)
    reference = build_canonical_reference(problem)
    student = formalize_student_work(STUDENT_ANSWER, problem=problem, reference=reference)
    evidence = build_diagnosis_evidence(problem, reference, student)
    diagnosis_context = build_diagnosis_context(problem, reference, student, evidence)
    diagnosis_state, diagnosis = build_diagnosis(evidence, context=diagnosis_context)
    pedagogy_state, strategy, plan = build_pedagogy_artifacts(problem, reference, diagnosis, diagnosis_state)
    deterministic_hint = build_hint_result(
        problem,
        reference,
        diagnosis,
        plan,
        strategy=strategy,
        hint_mode=HINT_MODE,
        llm_client=None,
    )

    base_client = build_default_llm_client() if USE_LLM else None
    recording_client = RecordingLLMClient(base_client) if base_client is not None else None
    print(f"LLM client available = {base_client is not None}")

    final_hint = (
        build_hint_result(
            problem,
            reference,
            diagnosis,
            plan,
            strategy=strategy,
            hint_mode=HINT_MODE,
            llm_client=recording_client,
        )
        if recording_client is not None
        else deterministic_hint
    )

    _print_json("Input", {"problem_text": PROBLEM_TEXT, "student_answer": STUDENT_ANSWER})
    _print_json("Diagnosis State", diagnosis_state.model_dump(mode="json"))
    _print_json("Diagnosis", diagnosis.model_dump(mode="json"))
    _print_json("Pedagogy State", pedagogy_state.model_dump(mode="json"))
    _print_json("Hint Strategy", strategy.model_dump(mode="json"))
    _print_json("Hint Plan", plan.model_dump(mode="json"))
    _print_json("Deterministic Hint", deterministic_hint.model_dump(mode="json"))
    _print_json("Final Hint", final_hint.model_dump(mode="json"))
    _print_llm_attempts(
        recording_client.records if recording_client is not None else [],
        llm_requested=USE_LLM,
        llm_available=base_client is not None,
    )

    _print_header("Summary")
    print(f"Diagnosis label: {diagnosis.diagnosis_label.value}")
    print(f"Teacher move: {plan.teacher_move.value}")
    print(f"Deterministic verified: {deterministic_hint.verification_passed}")
    print(f"Final verified: {final_hint.verification_passed}")
    print(f"Hint text: {final_hint.hint_text}")
    return recording_client.records if recording_client is not None else []


if __name__ == "__main__":
    if not WRITE_OUTPUT_TO_FILE:
        main()
    else:
        buffer = io.StringIO()
        tee = _TeeStream(sys.stdout, buffer)
        with redirect_stdout(tee):
            raw_records = main()
        OUTPUT_PATH.write_text(buffer.getvalue(), encoding="utf-8")
        RAW_LLM_OUTPUT_PATH.write_text(json.dumps(raw_records, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved debug output to: {OUTPUT_PATH}")
        print(f"Saved raw LLM attempts to: {RAW_LLM_OUTPUT_PATH}")
