"""Simple terminal entrypoint for the full tutoring pipeline."""
from __future__ import annotations

from src.models import HintMode
from src.pipeline import run_tutoring_pipeline


# Demo inputs. Edit these values and run `python main_2.py`.
PROBLEM_TEXT = (
    "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount for every ticket bought that "
    "exceeds 10. How much did Mr. Benson pay in all?"
)
STUDENT_ANSWER = "12 * 40 = 480\n12 - 10 = 2\n5% of 40 = 2\n2 * 2 = 4\n480 - 4 = 474\nAnswer is 474."

# When True, the pipeline will try the configured model and safely fall back
# where needed.
USE_LLM = True

# Other options: HintMode.SCAFFOLDING, HintMode.PEDAGOGY_FOLLOWING
HINT_MODE = HintMode.NORMAL


def _enum_value(value: object) -> str:
    return getattr(value, "value", str(value))


def _format_standard_solution(reference) -> str:
    if reference.rendered_solution_text and reference.rendered_solution_text.strip():
        return reference.rendered_solution_text.strip()

    lines: list[str] = []
    steps = reference.chosen_plan.steps
    results = reference.execution_trace.step_results

    for index, step in enumerate(steps):
        result = results[index] if index < len(results) else None
        operation = _enum_value(step.operation)
        if result is None:
            lines.append(f"- {step.step_id}: {step.expression} [{operation}] -> {step.output_ref}")
            continue

        if result.success and result.output_value is not None:
            inputs = ", ".join(f"{value:g}" for value in result.resolved_inputs) if result.resolved_inputs else "-"
            lines.append(
                f"- {step.step_id}: {step.expression} [{operation}] | input = {inputs} | "
                f"{step.output_ref} = {result.output_value:g}"
            )
        else:
            error_text = result.error_message or "execution failed"
            lines.append(f"- {step.step_id}: {step.expression} [{operation}] | lỗi: {error_text}")

        if step.explanation:
            lines.append(f"  giải thích: {step.explanation}")

    lines.append(f"- Kết quả cuối: {reference.final_answer:g}")
    return "\n".join(lines)


def _format_diagnosis(result) -> str:
    lines = [f"- Nhãn: {_enum_value(result.diagnosis_label)}"]
    if result.subtype:
        lines.append(f"- Phân loại con: {result.subtype}")
    lines.append(f"- Vị trí lỗi: {_enum_value(result.localization)}")
    if result.target_step_id:
        lines.append(f"- Step mục tiêu: {result.target_step_id}")
    if result.supporting_evidence_types:
        lines.append("- Evidence chính: " + ", ".join(result.supporting_evidence_types))
    lines.append(f"- Tóm tắt: {result.summary}")
    lines.append(f"- Độ tin cậy: {result.confidence:.2f}")
    return "\n".join(lines)


def main() -> None:
    tutoring_result = run_tutoring_pipeline(
        problem_text=PROBLEM_TEXT,
        student_answer=STUDENT_ANSWER,
        hint_mode=HINT_MODE,
        use_llm=USE_LLM,
    )

    print("=" * 88)
    print("ĐỀ BÀI")
    print("=" * 88)
    print(PROBLEM_TEXT.strip())
    print()

    print("=" * 88)
    print("LỜI GIẢI HỌC SINH")
    print("=" * 88)
    print(STUDENT_ANSWER.strip())
    print()

    print("=" * 88)
    print("LỜI GIẢI CHUẨN")
    print("=" * 88)
    print(_format_standard_solution(tutoring_result.reference))
    print()

    print("=" * 88)
    print("CHẨN ĐOÁN")
    print("=" * 88)
    print(_format_diagnosis(tutoring_result.diagnosis))
    print()

    print("=" * 88)
    print("HINT CUỐI")
    print("=" * 88)
    print(tutoring_result.hint_result.hint_text.strip())
    print()


if __name__ == "__main__":
    main()
