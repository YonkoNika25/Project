"""Artifact-first entrypoint for the full tutoring pipeline."""
from __future__ import annotations

from pathlib import Path

from src.models import HintMode
from src.pipeline.debug_runner import run_debug_pipeline


# Demo inputs. Edit these values and run `python main.py`.
PROBLEM_TEXT = (
    "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount for every ticket bought that "
    "exceeds 10. How much did Mr. Benson pay in all?"
)
STUDENT_ANSWER = "12 * 40 = 480\n12 - 10 = 2\n5% of 40 = 2\n2 * 2 = 4\n480 - 4 = 474\nAnswer is 474."

# When True, the pipeline will try the configured OpenRouter model and fall back
# safely to deterministic logic if an LLM step fails.
USE_LLM = True

# Other options: HintMode.SCAFFOLDING, HintMode.PEDAGOGY_FOLLOWING
HINT_MODE = HintMode.NORMAL

OUTPUT_ROOT = Path("debug_pipeline_artifacts")


def main() -> Path:
    print("Tutoring Pipeline Debug Runner")
    print(f"USE_LLM = {USE_LLM}")
    print(f"HINT_MODE = {HINT_MODE.value}")
    output_dir = run_debug_pipeline(
        problem_text=PROBLEM_TEXT,
        student_answer=STUDENT_ANSWER,
        hint_mode=HINT_MODE,
        use_llm=USE_LLM,
        output_root=OUTPUT_ROOT,
    )
    print(f"Saved artifact bundle to: {output_dir}")
    return output_dir


if __name__ == "__main__":
    main()
