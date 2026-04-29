"""Artifact-first debugger for the problem -> canonical reference pipeline."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from src.formalizer import formalize_problem
from src.formalizer.problem_formalizer_builder import (
    _build_formalized_problem_from_skeleton,
    _heuristic_formalize_problem,
    _merge_semantic_and_commitment_payloads,
)
from src.llm import LLMClient, LLMGenerationError, OpenRouterLLMClient, build_default_llm_client
from src.runtime import build_canonical_reference, compile_executable_plan, execute_plan, validate_problem_graph


# Edit these values, then run:
#   .\venv\Scripts\python.exe debug_formalizer.py
PROBLEM_TEXT = (
    "A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. "
    "Over three hundred years, it has consumed 847 people. Ships have been built larger over time, so each new "
    "ship has twice as many people as the last ship. How many people were on the ship the monster ate in the "
    "first hundred years?"
)
USE_LLM = True
OUTPUT_ROOT = Path("debug_formalizer_artifacts")


def _print_header(title: str) -> None:
    line = "=" * 20
    print(f"\n{line} {title} {line}")


def _extract_feedback_block(user_prompt: str) -> str | None:
    marker = "Structured feedback from the previous failed attempt:\n"
    if marker not in user_prompt:
        return None
    tail = user_prompt.split(marker, 1)[1]
    for end_marker in (
        "\n\nAnchor evidence pack for reference only:",
        "\n\nReturn only the JSON object.",
    ):
        if end_marker in tail:
            tail = tail.split(end_marker, 1)[0]
    return tail.strip()


def _model_json(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return _model_json(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _model_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_model_json(item) for item in value]
    if isinstance(value, set):
        return [_model_json(item) for item in sorted(value, key=str)]
    if isinstance(value, Path):
        return str(value)
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(_model_json(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _build_run_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"run_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _task_records(records: list[dict[str, Any]], task_name: str) -> list[dict[str, Any]]:
    return [record for record in records if record.get("task_name") == task_name]


def _last_successful_record(records: list[dict[str, Any]], task_name: str) -> tuple[dict[str, Any] | None, int | None]:
    task_specific_records = _task_records(records, task_name)
    for index in range(len(task_specific_records) - 1, -1, -1):
        record = task_specific_records[index]
        if record.get("status") == "success":
            return record, index + 1
    return None, None


def _prepare_semantic_payload(records: list[dict[str, Any]], problem_text: str) -> dict[str, Any] | None:
    record, attempt_index = _last_successful_record(records, "problem_formalizer_semantic_state")
    if record is None:
        return None
    payload = deepcopy(record["response"])
    payload["problem_text"] = problem_text.strip()
    notes = list(payload.get("notes", []))
    notes.append(f"llm_semantic_state_attempt:{attempt_index}")
    payload["notes"] = notes
    return payload


def _prepare_commitment_payload(records: list[dict[str, Any]], problem_text: str) -> dict[str, Any] | None:
    record, attempt_index = _last_successful_record(records, "problem_formalizer_executable_commitment")
    if record is None:
        return None
    payload = deepcopy(record["response"])
    payload["problem_text"] = problem_text.strip()
    notes = list(payload.get("notes", []))
    notes.append(f"llm_executable_commitment_attempt:{attempt_index}")
    payload["notes"] = notes
    return payload


class RecordingLLMClient:
    """Wrap an LLM client and record each formalizer attempt."""

    def __init__(self, base_client: LLMClient):
        self._base_client = base_client
        self.records: list[dict[str, Any]] = []

    def generate_json(
        self,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 120000,
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


def main() -> Path:
    run_dir = _build_run_dir()

    _print_header("Problem Formalizer Debugger")
    print(f"USE_LLM = {USE_LLM}")
    print(f"Artifact directory = {run_dir}")

    heuristic_problem, heuristic_evidence = _heuristic_formalize_problem(PROBLEM_TEXT)

    base_client = build_default_llm_client() if USE_LLM else None
    recording_client = RecordingLLMClient(base_client) if base_client is not None else None
    final_problem = (
        formalize_problem(PROBLEM_TEXT, llm_client=recording_client)
        if recording_client is not None
        else heuristic_problem
    )

    semantic_payload = (
        _prepare_semantic_payload(recording_client.records, PROBLEM_TEXT) if recording_client is not None else None
    )
    commitment_payload = (
        _prepare_commitment_payload(recording_client.records, PROBLEM_TEXT) if recording_client is not None else None
    )

    typed_problem_draft: Any = None
    typed_problem_draft_error: str | None = None
    if semantic_payload is not None and commitment_payload is not None:
        try:
            merged_payload = _merge_semantic_and_commitment_payloads(semantic_payload, commitment_payload)
            typed_problem_draft = _build_formalized_problem_from_skeleton(
                PROBLEM_TEXT,
                heuristic_problem,
                merged_payload,
            )
        except Exception as exc:
            merged_payload = _merge_semantic_and_commitment_payloads(semantic_payload, commitment_payload)
            typed_problem_draft = {
                "available": False,
                "error": str(exc),
            }
            typed_problem_draft_error = str(exc)
    else:
        merged_payload = None
        typed_problem_draft = {
            "available": False,
            "error": "semantic payload or commitment payload missing",
        }
        typed_problem_draft_error = "semantic payload or commitment payload missing"

    graph_validation = validate_problem_graph(final_problem)
    plan = compile_executable_plan(final_problem)
    trace = execute_plan(plan, final_problem) if plan.steps else None
    reference = None
    reference_error: str | None = None
    try:
        reference = build_canonical_reference(final_problem)
    except Exception as exc:
        reference_error = str(exc)

    meta = {
        "problem_text_length": len(PROBLEM_TEXT.strip()),
        "llm_requested": USE_LLM,
        "llm_available": base_client is not None,
        "heuristic_provenance": heuristic_problem.provenance.value,
        "final_provenance": final_problem.provenance.value,
        "graph_valid": graph_validation.is_valid,
        "graph_issue_codes": [issue.code for issue in graph_validation.issues],
        "plan_step_count": len(plan.steps),
        "execution_success": trace.success if trace is not None else False,
        "final_value": trace.final_value if trace is not None else None,
        "reference_available": reference is not None,
        "reference_error": reference_error,
        "typed_problem_draft_error": typed_problem_draft_error,
    }

    _write_json(run_dir / "00_run_meta.json", meta)
    _write_text(run_dir / "01_problem_text.txt", PROBLEM_TEXT.strip() + "\n")
    _write_json(run_dir / "02_heuristic_evidence_pack.json", heuristic_evidence)
    _write_json(
        run_dir / "03_problem_semantic_state.json",
        semantic_payload if semantic_payload is not None else {"available": False, "error": "no successful semantic payload"},
    )
    _write_json(
        run_dir / "04_plan_commitment.json",
        commitment_payload if commitment_payload is not None else {"available": False, "error": "no successful commitment payload"},
    )
    _write_json(
        run_dir / "05_typed_problem_draft_plus_problem_graph.json",
        typed_problem_draft,
    )
    _write_json(run_dir / "06_formalized_problem.json", final_problem)
    _write_json(run_dir / "07_executable_plan.json", plan)
    _write_json(run_dir / "08_execution_trace.json", trace if trace is not None else {"available": False})
    _write_json(
        run_dir / "09_canonical_reference.json",
        reference if reference is not None else {"available": False, "error": reference_error},
    )
    _write_json(run_dir / "10_graph_validation.json", graph_validation)
    _write_json(
        run_dir / "11_merged_llm_payload.json",
        merged_payload if merged_payload is not None else {"available": False},
    )
    _write_json(
        run_dir / "12_llm_attempts.json",
        recording_client.records if recording_client is not None else [],
    )

    summary_lines = [
        "Problem Formalizer Artifact Export",
        f"Artifact directory: {run_dir}",
        f"Heuristic provenance: {heuristic_problem.provenance.value}",
        f"Final provenance: {final_problem.provenance.value}",
        f"Graph valid: {graph_validation.is_valid}",
        f"Plan step count: {len(plan.steps)}",
        f"Execution success: {trace.success if trace is not None else False}",
        f"Final value: {trace.final_value if trace is not None else None}",
        f"Canonical reference available: {reference is not None}",
    ]
    _write_text(run_dir / "README.txt", "\n".join(summary_lines) + "\n")

    _print_header("Summary")
    for line in summary_lines:
        print(line)
    print("Artifacts written:")
    for artifact_path in sorted(run_dir.iterdir()):
        print(f"- {artifact_path.name}")

    return run_dir


if __name__ == "__main__":
    output_dir = main()
    print(f"\nSaved artifact bundle to: {output_dir}")
