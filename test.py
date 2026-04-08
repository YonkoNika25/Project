"""Direct smoke test for `problem + student answer -> LLM -> hint`."""
from __future__ import annotations

import json
from typing import Any

import requests

from src.llm import LLMGenerationError, OpenRouterLLMClient, build_default_llm_client


PROBLEM_TEXT = (
    "A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. "
    "Over three hundred years, it has consumed 847 people. Ships have been built larger over time, so each new "
    "ship has twice as many people as the last ship. How many people were on the ship the monster ate in the "
    "first hundred years?"
)

STUDENT_ANSWER = (
    "Let the first ship have x people.\n"
    "Then the next two ships had 3x and 4x people.\n"
    "x + 3x + 4x = 847\n"
    "8x = 847\n"
    "x = 121\n"
    "Answer is 121."
)

MAX_TOKENS = 10000


def build_direct_hint_prompts(problem_text: str, student_answer: str) -> tuple[str, str]:
    system_prompt = (
        "You are a careful math tutor. "
        "Read the problem and the student's solution. "
        "Identify the first meaningful mistake in the student's work and give a short hint. "
        "Do not reveal the final answer. "
        "Do not solve the whole problem. "
        "Return only a JSON object with these fields: "
        "mistake_step, why_wrong, hint_text."
    )
    user_prompt = (
        f"Problem:\n{problem_text}\n\n"
        f"Student solution:\n{student_answer}\n\n"
        "Requirements:\n"
        "- Focus on the first incorrect step.\n"
        "- If the student is correct, set mistake_step to \"none\".\n"
        "- Keep hint_text to at most two sentences.\n"
        "- Do not give the final numeric answer.\n\n"
        "Return JSON like:\n"
        "{\n"
        '  "mistake_step": "...",\n'
        '  "why_wrong": "...",\n'
        '  "hint_text": "..."\n'
        "}"
    )
    return system_prompt, user_prompt


def generate_and_record_json(
    client: OpenRouterLLMClient,
    task_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> dict[str, Any]:
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
        parsed = client._parse_json_content(content)
    except requests.RequestException as exc:
        raise LLMGenerationError(f"{task_name} request failed: {exc}") from exc
    except Exception as exc:
        raise LLMGenerationError(f"{task_name} response parsing failed: {exc}") from exc

    return {
        "request_payload": request_payload,
        "raw_response_text": raw_text,
        "raw_response_json": raw_json,
        "parsed_response": parsed,
    }


def main() -> None:
    base_client = build_default_llm_client()
    if base_client is None:
        raise RuntimeError("No default LLM client available. Check your .env OpenRouter settings.")
    if not isinstance(base_client, OpenRouterLLMClient):
        raise RuntimeError("This smoke test expects an OpenRouterLLMClient.")

    system_prompt, user_prompt = build_direct_hint_prompts(PROBLEM_TEXT, STUDENT_ANSWER)
    result = generate_and_record_json(
        base_client,
        task_name="direct_hint_only",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.2,
        max_tokens=MAX_TOKENS,
    )

    print("=== INPUT ===")
    print(json.dumps(
        {
            "problem_text": PROBLEM_TEXT,
            "student_answer": STUDENT_ANSWER,
        },
        indent=2,
        ensure_ascii=False,
    ))

    print("\n=== SYSTEM PROMPT ===")
    print(system_prompt)

    print("\n=== USER PROMPT ===")
    print(user_prompt)

    print("\n=== PARSED RESPONSE ===")
    print(json.dumps(result["parsed_response"], indent=2, ensure_ascii=False))

    print("\n=== RAW RESPONSE JSON ===")
    print(json.dumps(result["raw_response_json"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
