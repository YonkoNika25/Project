# Neuro-Symbolic Math Tutor (Phase 1)

A solver-grounded math tutoring system for multi-step word problems (GSM8K-style). The system uses a Large Language Model (Qwen2.5-Math) to generate reference solutions, diagnose student errors according to a pedagogical taxonomy, and provide targeted, non-spoiling hints.

## 🚀 Key Features

- **Reference Solver + Parser:** Generates step-by-step solutions via Qwen2.5-Math and parses `#### <answer>` into structured `ReferenceSolution`.
- **Answer Checker:** Robust normalization and comparison of student and reference answers.
- **Diagnosis Engine:** Classifies student errors (Arithmetic, Relation, Target Misunderstanding, etc.).
- **Pedagogical Hinting:** Generates conceptual, relational, or next-step hints.
- **Non-Spoiler Verification:** Automated check to ensure hints do not reveal the final answer.
- **Fallback System:** Reliable Vietnamese hints if the generative pipeline fails.

## 🛠️ Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Set your Hugging Face Token in a `.env` file:
    ```text
    HF_TOKEN=hf_your_token_here
    ```

## 🖥️ Usage

Run the end-to-end demo script:
```bash
python main.py
```

Run a small evaluation harness (recommended for research iterations):
```bash
python run_eval.py --split test --limit 50
```

## 🧪 Testing

Run normalized unit tests:
```bash
pytest
```

## 🏗️ Architecture

- `src/solver`: LLM client and parsing.
- `src/checker`: Answer comparison logic.
- `src/diagnosis`: Error classification engine.
- `src/hint`: Hint generation and verification pipeline.
- `src/models`: Shared Pydantic data contracts.
- `src/utils`: Shared utilities (LLM adapters).


### Model Configuration

`src/utils/llm_client.py` defaults to `Qwen/Qwen2.5-Math-7B-Instruct` to stay aligned with solver settings.
You can override this with:

```bash
export HF_MODEL_ID="Qwen/Qwen2.5-Math-7B-Instruct"
```
