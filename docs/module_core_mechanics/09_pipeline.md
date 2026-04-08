# Pipeline Mechanics

Based on:

- `src/pipeline/runner.py`

## Entry

`run_tutoring_pipeline(problem_text, student_answer, hint_mode=normal, llm_client=None, use_llm=True)`

## LLM client resolution

1. if explicit client is passed, use it
2. else if `use_llm=True`, build default client from environment
3. else run deterministic path

## Fixed pipeline order

1. `formalize_problem(...)`
2. `build_canonical_reference(problem)`
3. `formalize_student_work(...)`
4. `build_diagnosis_evidence(problem, reference, student_work)`
5. `diagnose(evidence, llm_client=...)`
6. `build_hint_plan(problem, reference, diagnosis)`
7. `build_hint_result(problem, reference, diagnosis, hint_plan, ...)`

## Hard dependency

The strongest gate is canonical reference construction:

- if the problem cannot be compiled/executed into a reference, the rest of the tutoring pipeline cannot proceed

## Output

The final `TutoringResult` packages:

1. problem
2. reference
3. student work
4. evidence
5. diagnosis
6. hint plan
7. hint result
