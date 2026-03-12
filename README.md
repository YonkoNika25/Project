# Neuro-Symbolic Math Tutor (Phase 1)

A solver-grounded math tutoring system for multi-step word problems (GSM8K-style). The system uses a Large Language Model (Qwen2.5-Math) to generate reference solutions, diagnose student errors according to a pedagogical taxonomy, and provide targeted, non-spoiling hints.

## 🚀 Key Features

- **Reference Solver + Parser:** Generates step-by-step solutions via Qwen2.5-Math and parses `#### <answer>` into structured `ReferenceSolution`.
- **Answer Checker:** Robust normalization and comparison of student and reference answers.
- **Symbolic Verifier (Phase 2):** Builds lightweight symbolic state + verification flags before diagnosis.
- **Diagnosis Engine:** Classifies student errors (Arithmetic, Relation, Target Misunderstanding, etc.) with symbolic evidence fusion.
- **Pedagogical Hinting:** Generates conceptual, relational, or next-step hints.
- **Hint Verification (Phase 2):** Automated spoiler + pedagogical alignment checks for generated hints.
- **Fallback System:** Reliable Vietnamese hints if the generative pipeline fails.

## 🛠️ Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Set your OpenRouter key in a `.env` file:
    ```text
    OPENROUTER_API_KEY=your_openrouter_key
    OPENROUTER_MODEL=qwen/qwen2.5-7b-instruct
    ```

## 🖥️ Usage

Run the end-to-end demo script:
```bash
python main.py
```

Run a small evaluation harness (recommended for research iterations):
```bash
python run_eval.py --split test --limit 50 --audit-output artifacts/eval_audit.jsonl --calibration-bins 10 --ablation-no-symbolic
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

`src/utils/llm_client.py` now uses OpenRouter by default.
You can configure model and endpoint with:

```bash
export OPENROUTER_API_KEY="your_key"
export OPENROUTER_MODEL="qwen/qwen2.5-7b-instruct"
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
```

For labeled diagnosis evaluation, pass a labels file (`.json/.jsonl/.csv`) to `run_eval.py`:

```bash
python run_eval.py --split test --limit 50 --audit-labels data/diagnosis_labels.jsonl --audit-output artifacts/eval_audit.jsonl --calibration-bins 10 --ablation-no-symbolic
```
