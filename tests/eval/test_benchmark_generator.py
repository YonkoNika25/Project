from src.dataset.gsm8k_loader import load_gsm8k_from_records
from src.eval.benchmark_generator import (
    generate_benchmark_bundle,
    generate_candidate_samples,
    score_problem_for_benchmark,
    select_base_problems,
)
from src.models import DiagnosisLabel


SAMPLE_RECORDS = [
    {
        "question": "Juan has 5 apples. He buys 3 more apples. How many apples does he have now?",
        "answer": "Juan has 5 apples and buys 3 more, so 5 + 3 = 8.\n#### 8",
    },
    {
        "question": "Lan has 10 candies. She gives 3 candies to her friend. How many candies does she have left?",
        "answer": "Lan starts with 10 candies and gives away 3, so 10 - 3 = 7.\n#### 7",
    },
    {
        "question": "What is 7 times 3?",
        "answer": "7 * 3 = 21\n#### 21",
    },
    {
        "question": "Julie is reading a 120-page book. Yesterday, she was able to read 12 pages and today, she read twice as many pages as yesterday. If she wants to read half of the remaining pages tomorrow, how many pages should she read?",
        "answer": (
            "Maila read 12 x 2 = <<12*2=24>>24 pages today.\n"
            "So she was able to read a total of 12 + 24 = <<12+24=36>>36 pages since yesterday.\n"
            "There are 120 - 36 = <<120-36=84>>84 pages left to be read.\n"
            "Since she wants to read half of the remaining pages tomorrow, then she should read 84/2 = <<84/2=42>>42 pages.\n"
            "#### 42"
        ),
    },
    {
        "question": "Carly collected 7 starfish with 5 arms each and one seastar with 14 arms. How many arms do the animals she collected have in total?",
        "answer": "7 * 5 = 35. Then 35 + 14 = 49.\n#### 49",
    },
]


def test_select_base_problems_prefers_clear_add_sub_records():
    records, _ = load_gsm8k_from_records(SAMPLE_RECORDS, split="train")
    selected, scores = select_base_problems(records, limit=2)

    assert len(selected) == 2
    assert all(score.score >= scores[-1].score for score in scores)
    selected_ids = {record.id for record in selected}
    assert "gsm8k_train_00002" not in selected_ids
    assert selected_ids.issubset({"gsm8k_train_00000", "gsm8k_train_00001", "gsm8k_train_00003"})


def test_generate_candidate_samples_for_subtractive_problem_covers_all_main_labels():
    records, _ = load_gsm8k_from_records(SAMPLE_RECORDS, split="train")
    subtractive = records[1]

    samples = generate_candidate_samples(
        subtractive,
        split="dev_audit",
        max_cases_per_problem=4,
        problem_index=0,
    )
    labels = {sample.gold_diagnosis.primary_label for sample in samples}

    assert DiagnosisLabel.CORRECT_ANSWER in labels
    assert DiagnosisLabel.ARITHMETIC_ERROR in labels
    assert DiagnosisLabel.QUANTITY_RELATION_ERROR in labels
    assert DiagnosisLabel.TARGET_MISUNDERSTANDING in labels


def test_generate_benchmark_bundle_assigns_problem_level_splits():
    records, _ = load_gsm8k_from_records(SAMPLE_RECORDS[:2], split="train")
    bundle = generate_benchmark_bundle(records, base_problem_limit=2, max_cases_per_problem=3)

    assert len(bundle.selected_problems) == 2
    assert len(bundle.samples) >= 4

    problem_to_splits: dict[str, set[str]] = {}
    for sample in bundle.samples:
        problem_to_splits.setdefault(sample.source_problem_id, set()).add(sample.split)

    assert all(len(splits) == 1 for splits in problem_to_splits.values())


def test_score_problem_for_benchmark_returns_reason_breakdown():
    records, _ = load_gsm8k_from_records(SAMPLE_RECORDS, split="train")
    score = score_problem_for_benchmark(records[0])

    assert score.problem_id == records[0].id
    assert score.score > 0
    assert any(reason.startswith("target_clarity=") for reason in score.reasons)


def test_multi_step_problem_annotation_detected_for_twice_and_half_problem():
    records, _ = load_gsm8k_from_records(SAMPLE_RECORDS, split="train")
    julie = records[3]

    sample = generate_candidate_samples(
        julie,
        split="dev_audit",
        max_cases_per_problem=3,
        problem_index=0,
    )[0]

    assert sample.problem.requires_multi_step is True
    assert sample.symbolic_annotation.target_text == (
        "If she wants to read half of the remaining pages tomorrow, how many pages should she read?"
    )


def test_relation_error_for_multi_quantity_additive_problem_prefers_partial_sum():
    records, _ = load_gsm8k_from_records(SAMPLE_RECORDS, split="train")
    carly = records[4]

    samples = generate_candidate_samples(
        carly,
        split="dev_audit",
        max_cases_per_problem=4,
        problem_index=0,
    )
    relation_sample = next(
        sample for sample in samples
        if sample.gold_diagnosis.primary_label == DiagnosisLabel.QUANTITY_RELATION_ERROR
    )

    assert relation_sample.student_case.error_generation_method == "partial_sum_only"
    assert relation_sample.student_case.student_answer_value == 12.0
