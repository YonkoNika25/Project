"""Standalone debugger for the diagnosis module."""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import requests

from src.diagnosis import build_diagnosis, diagnose
from src.evidence import build_diagnosis_context, build_diagnosis_evidence
from src.formalizer import formalize_problem, formalize_student_work
from src.llm import LLMClient, LLMGenerationError, OpenRouterLLMClient, build_default_llm_client
from src.runtime import build_canonical_reference


PROBLEM_TEXT = (
    "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount "
    "for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?"
)
STUDENT_ANSWER = "12 * 40 = 480\n12 - 10 = 2\n5% of 40 = 2\n2 * 2 = 4\n480 - 4 = 474\nAnswer is 474."
USE_LLM = True
WRITE_OUTPUT_TO_FILE = True
OUTPUT_PATH = Path("debug_diagnosis_output.txt")
RAW_LLM_OUTPUT_PATH = Path("debug_diagnosis_llm_raw.json")


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


def _note_value(notes: list[str], prefix: str) -> str | None:
    for note in notes:
        if note.startswith(prefix):
            return note.split(":", 1)[1]
    return None


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
    print("Diagnosis Debugger")
    print(f"USE_LLM = {USE_LLM}")

    problem = formalize_problem(PROBLEM_TEXT)
    reference = build_canonical_reference(problem)
    student = formalize_student_work(STUDENT_ANSWER, problem=problem, reference=reference)
    evidence = build_diagnosis_evidence(problem, reference, student)
    context = build_diagnosis_context(problem, reference, student, evidence)
    deterministic_state, deterministic = build_diagnosis(evidence, context=context, llm_client=None)

    base_client = build_default_llm_client() if USE_LLM else None
    recording_client = RecordingLLMClient(base_client) if base_client is not None else None
    print(f"LLM client available = {base_client is not None}")

    final_state, final_diagnosis = (
        build_diagnosis(evidence, context=context, llm_client=recording_client)
        if recording_client is not None
        else (deterministic_state, deterministic)
    )

    _print_json("Input", {"problem_text": PROBLEM_TEXT, "student_answer": STUDENT_ANSWER})
    _print_json("Student Work", student.model_dump(mode="json"))
    _print_json("Evidence", evidence.model_dump(mode="json"))
    _print_json("Diagnosis Context", context.model_dump(mode="json"))
    _print_json("Deterministic Diagnosis State", deterministic_state.model_dump(mode="json"))
    _print_json("Deterministic Diagnosis", deterministic.model_dump(mode="json"))
    _print_json("Final Diagnosis State", final_state.model_dump(mode="json"))
    _print_json("Final Diagnosis", final_diagnosis.model_dump(mode="json"))
    _print_llm_attempts(
        recording_client.records if recording_client is not None else [],
        llm_requested=USE_LLM,
        llm_available=base_client is not None,
    )

    _print_header("Summary")
    print(f"Deterministic label: {deterministic.diagnosis_label.value}")
    print(f"Final label: {final_diagnosis.diagnosis_label.value}")
    print(f"Answer acceptability: {final_state.answer_acceptability.value}")
    print(f"Target alignment: {final_state.target_alignment.value}")
    print(f"Process equivalence: {final_state.process_equivalence.value}")
    print(f"Intervention required: {final_state.intervention_required}")
    print(f"Localization: {final_diagnosis.localization.value}")
    print(f"Target step: {final_diagnosis.target_step_id}")
    print(f"Used llm-first diagnosis: {'llm_first_diagnosis_used' in final_diagnosis.notes}")
    print(f"Fell back to deterministic: {'llm_diagnosis_failed_fallback' in final_diagnosis.notes}")
    print(f"Failure stage: {_note_value(final_diagnosis.notes, 'llm_diagnosis_failure_stage:')}")
    print(f"Failure reason: {_note_value(final_diagnosis.notes, 'llm_diagnosis_failure_reason:')}")
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
