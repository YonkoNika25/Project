import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def openrouter_llm_adapter(prompt: str) -> str:
    """Adapter for OpenRouter chat completions API.

    Uses OPENROUTER_API_KEY from environment variables.
    Optional env vars:
    - OPENROUTER_MODEL (default: qwen/qwen2.5-7b-instruct)
    - OPENROUTER_BASE_URL (default: https://openrouter.ai/api/v1)
    - OPENROUTER_HTTP_REFERER / OPENROUTER_APP_NAME (optional headers)
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPENROUTER_API_KEY not found in environment variables.")
        return "Error: OPENROUTER_API_KEY is missing."

    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model_id = os.environ.get("OPENROUTER_MODEL", "qwen/qwen2.5-7b-instruct")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    referer = os.environ.get("OPENROUTER_HTTP_REFERER")
    app_name = os.environ.get("OPENROUTER_APP_NAME")
    if referer:
        headers["HTTP-Referer"] = referer
    if app_name:
        headers["X-Title"] = app_name

    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return content.strip()
    except Exception as exc:
        logger.error("OpenRouter API call failed: %s", exc)
        return f"Error calling LLM: {exc}"


# Backward-compatible alias used across pipeline.
def hf_llm_adapter(prompt: str) -> str:
    return openrouter_llm_adapter(prompt)
