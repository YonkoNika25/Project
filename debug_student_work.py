"""Standalone debugger for the student-work formalization + graph flow."""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import requests

from src.formalizer import formalize_problem, formalize_student_work
from src.llm import LLMClient, OpenRouterLLMClient, build_default_llm_client


# Edit these values, then run:
#   .\venv\Scripts\python.exe debug_student_work.py
PROBLEM_TEXT = (
    "A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. Over three hundred years, it has consumed 847 people. Ships have been built larger over time, so each new ship has twice as many people as the last ship. How many people were on the ship the monster ate in the first hundred years?"
    
)
STUDENT_ANSWER = "Let the first ship have x people.Then the next two ships had 2x and 4x people.x + 2x + 4x = 847. 7x = 847. x = 847/7. x = 117.Answer is 117."

USE_LLM = True
WRITE_OUTPUT_TO_FILE = True
OUTPUT_PATH = Path("debug_student_work_output.txt")
RAW_LLM_OUTPUT_PATH = Path("debug_student_work_llm_raw.json")


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


def _extract_feedback_block(user_prompt: str) -> str | None:
    marker = "Structured feedback from the previous failed attempt:\n"
    if marker not in user_prompt:
        return None
    tail = user_prompt.split(marker, 1)[1]
    end_markers = [
        "\n\nCompact problem context:\n",
        "\n\nCompact heuristic draft:\n",
        "\n\nReturn only the JSON object.",
    ]
    for end_marker in end_markers:
        if end_marker in tail:
            tail = tail.split(end_marker, 1)[0]
            break
    return tail.strip()


class RecordingLLMClient:
    """Wrap an LLM client and record each student-work attempt."""

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
        feedback = _extract_feedback_block(user_prompt)
        if isinstance(self._base_client, OpenRouterLLMClient):
            return self._generate_json_openrouter(
                task_name=task_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                feedback=feedback,
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
                    "feedback": feedback,
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
                "feedback": feedback,
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
        feedback: str | None,
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
                    "feedback": feedback,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "error": f"{task_name} request failed: {exc}",
                    "request_payload": request_payload,
                    "raw_response_text": raw_text,
                    "raw_response_json": raw_json,
                }
            )
            raise LLMGenerationError(f"{task_name} request failed: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            self.records.append(
                {
                    "task_name": task_name,
                    "status": "error",
                    "feedback": feedback,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "error": f"{task_name} response shape was invalid",
                    "request_payload": request_payload,
                    "raw_response_text": raw_text,
                    "raw_response_json": raw_json,
                }
            )
            raise LLMGenerationError(f"{task_name} response shape was invalid") from exc
        except Exception as exc:
            self.records.append(
                {
                    "task_name": task_name,
                    "status": "error",
                    "feedback": feedback,
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
                "feedback": feedback,
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
        feedback = record.get("feedback")
        if feedback:
            print("Feedback issues passed into this attempt:")
            print(feedback)
        else:
            print("Feedback issues passed into this attempt: []")

        system_prompt = record.get("system_prompt")
        user_prompt = record.get("user_prompt")
        if system_prompt:
            print("System prompt sent to model:")
            print(system_prompt)
        if user_prompt:
            print("User prompt sent to model:")
            print(user_prompt)

        if record["status"] == "success":
            print("LLM response:")
            print(json.dumps(record["response"], indent=2, ensure_ascii=False))
        else:
            print(f"Error: {record['error']}")


def _summarize_attempts(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for record in records:
        task_name = record.get("task_name", "unknown")
        task_summary = summary.setdefault(
            task_name,
            {
                "attempt_count": 0,
                "success_count": 0,
                "error_count": 0,
            },
        )
        task_summary["attempt_count"] += 1
        if record.get("status") == "success":
            task_summary["success_count"] += 1
        else:
            task_summary["error_count"] += 1
    return summary


def main() -> list[dict[str, Any]]:
    print("Student Work Debugger")
    print(f"USE_LLM = {USE_LLM}")

    base_client = build_default_llm_client() if USE_LLM else None
    recording_client = RecordingLLMClient(base_client) if base_client is not None else None
    print(f"LLM client available = {base_client is not None}")

    problem = formalize_problem(
        PROBLEM_TEXT,
        llm_client=base_client if base_client is not None else None,
    )

    heuristic_student = formalize_student_work(
        STUDENT_ANSWER,
        problem=problem,
        llm_client=None,
    )

    final_student = (
        formalize_student_work(
            STUDENT_ANSWER,
            problem=problem,
            llm_client=recording_client,
        )
        if recording_client is not None
        else heuristic_student
    )

    _print_json(
        "Input",
        {
            "problem_text": PROBLEM_TEXT,
            "student_answer": STUDENT_ANSWER,
        },
    )
    _print_json("Problem", problem.model_dump(mode="json"))
    _print_json("Heuristic Student Work", heuristic_student.model_dump(mode="json"))
    _print_json("Final Student Work", final_student.model_dump(mode="json"))
    _print_json(
        "Student Graph",
        final_student.student_graph.model_dump(mode="json") if final_student.student_graph is not None else None,
    )
    _print_llm_attempts(
        recording_client.records if recording_client is not None else [],
        llm_requested=USE_LLM,
        llm_available=base_client is not None,
    )

    _print_header("Summary")
    print(f"Heuristic mode: {heuristic_student.mode.value}")
    print(f"Final mode: {final_student.mode.value}")
    print(f"Heuristic final answer: {heuristic_student.normalized_final_answer}")
    print(f"Final final answer: {final_student.normalized_final_answer}")
    print(f"Selected target ref: {final_student.selected_target_ref}")
    print(f"Student graph present: {final_student.student_graph is not None}")
    print(
        f"Student graph target node: "
        f"{final_student.student_graph.target_node_id if final_student.student_graph is not None else None}"
    )
    print(f"Student-side fallback notes: {[note for note in final_student.notes if 'llm_student_' in note or 'student_graph_issue:' in note]}")
    _print_json(
        "LLM Attempt Summary",
        _summarize_attempts(recording_client.records if recording_client is not None else []),
    )
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
        RAW_LLM_OUTPUT_PATH.write_text(
            json.dumps(raw_records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nSaved debug output to: {OUTPUT_PATH}")
        print(f"Saved raw LLM attempts to: {RAW_LLM_OUTPUT_PATH}")
