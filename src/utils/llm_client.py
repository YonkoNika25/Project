import os
import logging
import requests
import json
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env if present

logger = logging.getLogger(__name__)


def openrouter_llm_adapter(prompt: str) -> str:
    """Adapter for OpenRouter API.

    Uses OPENROUTER_API_KEY from environment variables.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPENROUTER_API_KEY not found in environment variables.")
        return "Error: OPENROUTER_API_KEY is missing."

    try:
        # User specified qwen/qwen-2.5-7b-instruct
        model_id = os.environ.get("OPENROUTER_MODEL_ID", "qwen/qwen-2.5-7b-instruct")
        timeout_seconds = float(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "30"))

        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(
                {
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                    "temperature": 0.1,  # Low temperature for reasoning tasks
                }
            ),
            timeout=timeout_seconds,
        )

        if response.status_code != 200:
            logger.error(f"OpenRouter API call failed: {response.status_code} {response.text}")
            return f"Error calling LLM: {response.text}"

        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return content.strip()
    except Exception as exc:
        logger.error(f"OpenRouter API call failed: {exc}")
        return f"Error calling LLM: {exc}"


# Backward-compatible alias used across pipeline.
def hf_llm_adapter(prompt: str) -> str:
    return openrouter_llm_adapter(prompt)
