import os
import logging
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv() # Load HF_TOKEN from .env if present

logger = logging.getLogger(__name__)

def hf_llm_adapter(prompt: str) -> str:
    """Adapter for Hugging Face Inference API.
    
    Uses HF_TOKEN from environment variables.
    """
    api_key = os.environ.get("HF_TOKEN")
    if not api_key:
        logger.error("HF_TOKEN not found in environment variables.")
        return "Error: HF_TOKEN is missing."

    try:
        client = InferenceClient(api_key=api_key)
        
        # Using a model that is often available on free Serverless Inference
        model_id = os.environ.get("HF_MODEL_ID", "Qwen/Qwen2.5-Math-7B-Instruct")
        
        completion = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=1024,
            temperature=0.1, # Low temperature for reasoning tasks
        )
        
        content = completion.choices[0].message.content
        return content.strip()
        
    except Exception as exc:
        logger.error(f"HF Inference API call failed: {exc}")
        return f"Error calling LLM: {exc}"
