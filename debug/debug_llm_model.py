"""Minimal OpenRouter model smoke test for the repo's .env configuration."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.input_loader import DEFAULT_PROBLEM_PATH, load_problem_text

DEBUG_OUTPUT_DIR = PROJECT_ROOT / "debug" / "ouput"
DEBUG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _mask_secret(value: str | None, visible: int = 6) -> str:
    if not value:
        return "<missing>"
    if len(value) <= visible * 2:
        return value[:visible] + "..."
    return f"{value[:visible]}...{value[-visible:]}"


def _extract_content(data: dict[str, Any]) -> str:
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        return "<no assistant content found>"


def _try_parse_json_text(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def main() -> int:
    problem_text = load_problem_text()
    load_dotenv()

    api_key = os.getenv("OPENROUTER_API_KEY")
    model_id = os.getenv("OPENROUTER_MODEL_ID", "openai/gpt-5-nano")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    timeout_seconds = int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "45"))
    app_name = os.getenv("OPENROUTER_APP_NAME", "problem-formalizer")

    print("OpenRouter Model Smoke Test")
    print(f"OPENROUTER_BASE_URL = {base_url}")
    print(f"OPENROUTER_MODEL_ID = {model_id}")
    print(f"OPENROUTER_APP_NAME = {app_name}")
    print(f"OPENROUTER_API_KEY = {_mask_secret(api_key)}")

    if not api_key:
        print("\nNo OPENROUTER_API_KEY found in .env.")
        return 1

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": app_name,
    }
    payload = {
        "model": model_id,
        "temperature": 0,
        "max_tokens": 70000,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are testing a math word problem solver. "
                    "Return only a JSON object with keys "
                    "`requested_model_echo`, `problem_summary`, `target_question`, "
                    "`solution_steps`, `final_answer_guess`, and `answer_line`."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"The requested model id is `{model_id}`.\n\n"
                    f"Problem:\n{problem_text}\n\n"
                    "Please do all of the following:\n"
                    "1. Copy that exact model id into `requested_model_echo`.\n"
                    "2. Write a one-sentence `problem_summary`.\n"
                    "3. Put the question being asked into `target_question`.\n"
                    "4. Solve the problem and provide `solution_steps` as a JSON array of "
                    "short strings, one reasoning step per item.\n"
                    "5. Put the numeric result into `final_answer_guess`.\n"
                    "6. Put a final short string like `Answer: 476` into `answer_line`."
                ),
            },
        ],
    }

    print("\nSending request...")
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return 2

    try:
        data = response.json()
    except ValueError as exc:
        print(f"Response was not valid JSON: {exc}")
        print("\nRaw response text:")
        print(response.text)
        return 3

    print("\nRequest model:")
    print(model_id)

    print("\nProblem text:")
    print(problem_text)
    print(f"(loaded from {DEFAULT_PROBLEM_PATH})")

    print("\nResponse model:")
    print(data.get("model", "<missing>"))

    if "provider" in data:
        print("\nProvider:")
        print(data["provider"])

    assistant_content = _extract_content(data)
    print("\nAssistant raw content:")
    print(assistant_content)

    parsed_content = _try_parse_json_text(assistant_content)
    if parsed_content is not None:
        print("\nParsed assistant JSON:")
        print(json.dumps(parsed_content, indent=2, ensure_ascii=False))

        if "solution_steps" in parsed_content:
            print("\nSolution steps:")
            for index, step in enumerate(parsed_content.get("solution_steps") or [], start=1):
                print(f"{index}. {step}")

        if "final_answer_guess" in parsed_content:
            print("\nModel final answer guess:")
            print(parsed_content["final_answer_guess"])

        if "answer_line" in parsed_content:
            print("\nModel answer line:")
            print(parsed_content["answer_line"])

    print("\nFull top-level response keys:")
    print(sorted(data.keys()))

    output_path = DEBUG_OUTPUT_DIR / "debug_llm_model_output.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    print(f"\nSaved full response to {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
