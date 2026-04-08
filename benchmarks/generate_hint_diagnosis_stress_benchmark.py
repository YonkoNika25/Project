from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BASE_PATH = DATA_DIR / "hint_diagnosis_base_problems_50.json"
SAMPLES_PATH = DATA_DIR / "hint_diagnosis_stress_200.jsonl"
SUMMARY_PATH = DATA_DIR / "hint_diagnosis_stress_summary.json"


def _answer(lines: list[str], final_value: float | None) -> str:
    text = "\n".join(lines)
    return text if final_value is None else f"{text}\nAnswer is {final_value:g}."


def _problem(kind: str, problem_id: str, category: str, difficulty: str, **kwargs) -> dict:
    return {
        "kind": kind,
        "problem_id": problem_id,
        "category": category,
        "difficulty": difficulty,
        **kwargs,
    }


def build_base_problems() -> list[dict]:
    problems: list[dict] = []
    for i, x in enumerate([12, 17, 21, 28], 1):
        problems.append(_problem("consecutive", f"alg_consecutive_{i}", "algebra_variable", "medium", x=x))
    for i, (younger, gap) in enumerate([(12, 6), (19, 5), (24, 8)], 1):
        problems.append(_problem("age", f"alg_age_{i}", "algebra_variable", "medium", younger=younger, gap=gap))
    for i, (width, extra) in enumerate([(7, 5), (9, 4), (12, 8)], 1):
        problems.append(_problem("rect_width", f"alg_rectangle_{i}", "algebra_variable", "hard", width=width, extra=extra))

    for i, params in enumerate([(6, 14, 8), (9, 11, 5), (12, 9, 6), (7, 18, 12)], 1):
        problems.append(_problem("rate_fee", f"rate_fee_{i}", "unit_rate", "medium", unit_price=params[0], qty=params[1], fee=params[2]))
    for i, params in enumerate([(65, 3, 14), (72, 4, 18), (58, 5, 12), (84, 2, 25)], 1):
        problems.append(_problem("rate_distance", f"rate_distance_{i}", "unit_rate", "hard", speed=params[0], hours=params[1], extra=params[2]))

    for i, params in enumerate([(80, 25), (96, 15), (120, 20), (150, 30)], 1):
        problems.append(_problem("discount", f"percent_discount_{i}", "percent", "medium", price=params[0], percent=params[1]))
    for i, params in enumerate([(200, 10, 8), (180, 20, 5), (240, 15, 10), (320, 25, 8)], 1):
        problems.append(_problem("discount_tax", f"percent_tax_{i}", "percent", "hard", price=params[0], discount=params[1], tax=params[2]))

    for i, params in enumerate([(15, 8), (23, 12), (31, 10), (18, 14), (27, 9), (34, 16), (42, 18)], 1):
        problems.append(_problem("sum_diff", f"compare_{i}", "compare_sum_difference", "medium", smaller=params[0], diff=params[1]))

    for i, params in enumerate([(75, 23, 18), (64, 17, 12), (93, 28, 15), (120, 35, 22), (88, 19, 27)], 1):
        problems.append(_problem("balance", f"intermediate_{i}", "intermediate_target", "medium", start=params[0], spent=params[1], earned=params[2]))

    for i, first in enumerate([17, 23, 29, 41, 53], 1):
        problems.append(_problem("doubling", f"growth_{i}", "growth_pattern", "hard", first=first))

    for i, params in enumerate([(7, 5), (9, 6), (11, 4), (13, 7), (15, 8)], 1):
        problems.append(_problem("geom_area", f"geometry_{i}", "geometry", "medium", width=params[0], extra=params[1]))

    for i, first in enumerate([121, 77], 1):
        problems.append(_problem("monster", f"hard_parse_{i}", "hard_parse", "hard", first=first))

    if len(problems) != 50:
        raise ValueError(f"Expected 50 problems, got {len(problems)}")
    return problems


def _render(problem: dict) -> tuple[str, float, list[dict]]:
    k = problem["kind"]
    if k == "consecutive":
        x = problem["x"]; total = x + x + 1 + x + 2
        text = f"Three consecutive integers add up to {total}. What is the smallest integer?"
        variants = [
            ("correct_trace", _answer(["Let the smallest integer be x.", "Then the next two integers are x + 1 and x + 2.", f"x + (x + 1) + (x + 2) = {total}", f"3x = {total - 3}", f"x = {x}"], x), True, x),
            ("arithmetic_error", _answer(["Let the smallest integer be x.", f"x + (x + 1) + (x + 2) = {total}", f"3x = {total - 3}", f"x = {x + 1}"], x + 1), False, x + 1),
            ("relation_error", _answer(["Let the smallest integer be x.", "Then the next two integers are x + 2 and x + 4.", f"x + (x + 2) + (x + 4) = {total}", f"3x = {total - 6}", f"x = {(total - 6) / 3:g}"], (total - 6) / 3), False, (total - 6) / 3),
            ("target_confusion", _answer(["Let the smallest integer be x.", f"3x = {total - 3}", f"x = {x}", f"The middle integer is {x + 1}."], x + 1), False, x + 1),
            ("reordered_correct", _answer([f"Start from the total: {total} - 3 = {total - 3}.", f"So 3x = {total - 3}.", f"x = {x}."], x), True, x),
        ]
        return text, float(x), _pack_variants(variants, ["consecutive"])
    if k == "age":
        younger = problem["younger"]; gap = problem["gap"]; older = younger + gap; total = younger + older
        text = f"Lan is {gap} years older than Minh. Together they are {total} years old. How old is Minh?"
        variants = [
            ("correct_trace", _answer([f"Let Minh's age be x and Lan's age be x + {gap}.", f"x + (x + {gap}) = {total}", f"2x = {total - gap}", f"x = {younger}"], younger), True, younger),
            ("arithmetic_error", _answer([f"x + (x + {gap}) = {total}", f"2x = {total - gap}", f"x = {younger + 1}"], younger + 1), False, younger + 1),
            ("relation_error", _answer([f"Let Minh's age be x and Lan's age be x - {gap}.", f"x + (x - {gap}) = {total}", f"2x = {total + gap}", f"x = {(total + gap) / 2:g}"], (total + gap) / 2), False, (total + gap) / 2),
            ("target_confusion", _answer([f"x + (x + {gap}) = {total}", f"x = {younger}", f"So Lan is {older}."], older), False, older),
        ]
        return text, float(younger), _pack_variants(variants, ["age_equation"])
    if k == "rect_width":
        w = problem["width"]; extra = problem["extra"]; l = w + extra; p = 2 * (w + l)
        text = f"A rectangle has length {extra} cm more than its width. Its perimeter is {p} cm. What is the width?"
        variants = [
            ("correct_trace", _answer([f"Let the width be x and the length be x + {extra}.", f"2(x + x + {extra}) = {p}", f"4x = {p - 2 * extra}", f"x = {w}"], w), True, w),
            ("arithmetic_error", _answer([f"2(x + x + {extra}) = {p}", f"4x = {p - 2 * extra}", f"x = {w + 1}"], w + 1), False, w + 1),
            ("relation_error", _answer([f"x + (x + {extra}) = {p}", f"2x = {p - extra}", f"x = {(p - extra) / 2:g}"], (p - extra) / 2), False, (p - extra) / 2),
            ("target_confusion", _answer([f"2(x + x + {extra}) = {p}", f"x = {w}", f"So the length is {l}."], l), False, l),
        ]
        return text, float(w), _pack_variants(variants, ["geometry_linear_equation"])
    if k == "rate_fee":
        unit_price = problem["unit_price"]; qty = problem["qty"]; fee = problem["fee"]; subtotal = unit_price * qty; total = subtotal + fee
        text = f"A shop charges ${unit_price} for each notebook and a flat delivery fee of ${fee}. What is the total cost for {qty} notebooks?"
        variants = [
            ("correct_trace", _answer([f"{qty} * {unit_price} = {subtotal}", f"{subtotal} + {fee} = {total}"], total), True, total),
            ("arithmetic_error", _answer([f"{qty} * {unit_price} = {subtotal}", f"{subtotal} + {fee} = {total + 2}"], total + 2), False, total + 2),
            ("relation_error", _answer([f"{qty} + {unit_price} = {qty + unit_price}", f"{qty + unit_price} + {fee} = {qty + unit_price + fee}"], qty + unit_price + fee), False, qty + unit_price + fee),
            ("target_confusion", _answer([f"{qty} * {unit_price} = {subtotal}", "That is the total before the extra fee."], subtotal), False, subtotal),
            ("reordered_correct", _answer([f"The fee is {fee}.", f"The item total is {qty} * {unit_price} = {subtotal}.", f"Then {subtotal} + {fee} = {total}."], total), True, total),
        ]
        return text, float(total), _pack_variants(variants, ["rate_plus_fee"])
    if k == "rate_distance":
        speed = problem["speed"]; hours = problem["hours"]; extra = problem["extra"]; base = speed * hours; total = base + extra
        text = f"A train travels at {speed} km per hour for {hours} hours, then continues {extra} km farther to the station. How far did it travel in all?"
        variants = [
            ("correct_trace", _answer([f"{speed} * {hours} = {base}", f"{base} + {extra} = {total}"], total), True, total),
            ("arithmetic_error", _answer([f"{speed} * {hours} = {base}", f"{base} + {extra} = {total - 3}"], total - 3), False, total - 3),
            ("relation_error", _answer([f"{speed} + {hours} = {speed + hours}", f"{speed + hours} + {extra} = {speed + hours + extra}"], speed + hours + extra), False, speed + hours + extra),
            ("target_confusion", _answer([f"{speed} * {hours} = {base}", "That is the distance before the last extra part."], base), False, base),
        ]
        return text, float(total), _pack_variants(variants, ["distance_plus_extra"])
    if k == "discount":
        price = problem["price"]; percent = problem["percent"]; discount = price * percent / 100; total = price - discount
        text = f"A jacket costs ${price}. It is on sale for {percent}% off. What is the sale price?"
        variants = [
            ("correct_trace", _answer([f"{percent}% of {price} = {discount:g}", f"{price} - {discount:g} = {total:g}"], total), True, total),
            ("arithmetic_error", _answer([f"{percent}% of {price} = {discount:g}", f"{price} - {discount:g} = {total - 1:g}"], total - 1), False, total - 1),
            ("relation_error", _answer([f"{price} + {percent} = {price + percent}", f"So the sale price is {price + percent}."], price + percent), False, price + percent),
            ("target_confusion", _answer([f"{percent}% of {price} = {discount:g}", "That is the amount of the discount."], discount), False, discount),
        ]
        return text, float(total), _pack_variants(variants, ["discount_problem"])
    if k == "discount_tax":
        price = problem["price"]; d = problem["discount"]; t = problem["tax"]; disc = price * d / 100; discounted = price - disc; tax = discounted * t / 100; total = discounted + tax
        text = f"A tablet costs ${price}. A store gives a {d}% discount, and then charges {t}% tax on the discounted price. What is the final price?"
        variants = [
            ("correct_trace", _answer([f"{d}% of {price} = {disc:g}", f"{price} - {disc:g} = {discounted:g}", f"{t}% of {discounted:g} = {tax:g}", f"{discounted:g} + {tax:g} = {total:g}"], total), True, total),
            ("arithmetic_error", _answer([f"{d}% of {price} = {disc:g}", f"{price} - {disc:g} = {discounted:g}", f"{t}% of {discounted:g} = {tax:g}", f"{discounted:g} + {tax:g} = {total + 2:g}"], total + 2), False, total + 2),
            ("relation_error", _answer([f"{t}% of {price} = {price * t / 100:g}", f"{price} + {price * t / 100:g} = {price + price * t / 100:g}"], price + price * t / 100), False, price + price * t / 100),
            ("target_confusion", _answer([f"{d}% of {price} = {disc:g}", f"{price} - {disc:g} = {discounted:g}", "That is the discounted price before tax."], discounted), False, discounted),
        ]
        return text, float(total), _pack_variants(variants, ["discount_then_tax"])
    if k == "sum_diff":
        smaller = problem["smaller"]; diff = problem["diff"]; larger = smaller + diff; total = smaller + larger
        text = f"The sum of two numbers is {total}, and the larger number is {diff} more than the smaller number. What is the smaller number?"
        variants = [
            ("correct_trace", _answer(["Let the smaller number be x.", f"Then the larger number is x + {diff}.", f"x + (x + {diff}) = {total}", f"2x = {total - diff}", f"x = {smaller}"], smaller), True, smaller),
            ("arithmetic_error", _answer([f"x + (x + {diff}) = {total}", f"2x = {total - diff}", f"x = {smaller + 1}"], smaller + 1), False, smaller + 1),
            ("relation_error", _answer([f"Then the larger number is x - {diff}.", f"x + (x - {diff}) = {total}", f"2x = {total + diff}", f"x = {(total + diff) / 2:g}"], (total + diff) / 2), False, (total + diff) / 2),
            ("target_confusion", _answer([f"x + (x + {diff}) = {total}", f"x = {smaller}", f"So the larger number is {larger}."], larger), False, larger),
            ("reordered_correct", _answer([f"The total minus the difference is {total} - {diff} = {total - diff}.", f"So 2x = {total - diff}.", f"x = {smaller}."], smaller), True, smaller),
        ]
        return text, float(smaller), _pack_variants(variants, ["sum_difference"])
    if k == "balance":
        start = problem["start"]; spent = problem["spent"]; earned = problem["earned"]; mid = start - spent; total = mid + earned
        text = f"Mia had ${start}. She spent ${spent} on groceries and then earned ${earned} by tutoring. How much money does she have now?"
        variants = [
            ("correct_trace", _answer([f"{start} - {spent} = {mid}", f"{mid} + {earned} = {total}"], total), True, total),
            ("arithmetic_error", _answer([f"{start} - {spent} = {mid}", f"{mid} + {earned} = {total - 2}"], total - 2), False, total - 2),
            ("relation_error", _answer([f"{start} + {spent} = {start + spent}", f"{start + spent} + {earned} = {start + spent + earned}"], start + spent + earned), False, start + spent + earned),
            ("target_confusion", _answer([f"{start} - {spent} = {mid}", "That is how much remained after the shopping trip."], mid), False, mid),
        ]
        return text, float(total), _pack_variants(variants, ["two_step_balance"])
    if k == "doubling":
        first = problem["first"]; total = first + 2 * first + 4 * first; third = 4 * first
        text = f"A quantity doubles from one stage to the next. Over three stages, the total is {total}. What was the amount in the first stage?"
        variants = [
            ("correct_trace", _answer(["Let the first amount be x.", "Then the next two amounts are 2x and 4x.", f"x + 2x + 4x = {total}", f"7x = {total}", f"x = {first}"], first), True, first),
            ("arithmetic_error", _answer([f"x + 2x + 4x = {total}", f"7x = {total}", f"x = {first + 1}"], first + 1), False, first + 1),
            ("relation_error", _answer(["Then the next two amounts are 3x and 4x.", f"x + 3x + 4x = {total}", f"8x = {total}", f"x = {total / 8:g}"], total / 8), False, total / 8),
            ("target_confusion", _answer([f"x + 2x + 4x = {total}", f"7x = {total}", f"x = {first}", f"The third amount is {third}."], third), False, third),
        ]
        return text, float(first), _pack_variants(variants, ["doubling_sequence"])
    if k == "geom_area":
        width = problem["width"]; extra = problem["extra"]; length = width + extra; area = width * length
        text = f"A rectangle has width {width} cm and length {extra} cm more than the width. What is its area?"
        variants = [
            ("correct_trace", _answer([f"The width is {width}.", f"The length is {width} + {extra} = {length}.", f"{width} * {length} = {area}"], area), True, area),
            ("arithmetic_error", _answer([f"The width is {width}.", f"The length is {width} + {extra} = {length}.", f"{width} * {length} = {area + 4}"], area + 4), False, area + 4),
            ("relation_error", _answer([f"The width is {width}.", f"The length is {width} + {extra} = {length}.", f"{width} + {length} = {width + length}"], width + length), False, width + length),
            ("target_confusion", _answer([f"The width is {width}.", f"The length is {width} + {extra} = {length}.", "So the missing length is found."], length), False, length),
        ]
        return text, float(area), _pack_variants(variants, ["geometry_area"])
    if k == "monster":
        first = problem["first"]; total = first + 2 * first + 4 * first; third = 4 * first
        text = (
            f"A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. "
            f"Over three hundred years, it has consumed {total} people. Ships have been built larger over time, so each new "
            "ship has twice as many people as the last ship. How many people were on the ship the monster ate in the first hundred years?"
        )
        variants = [
            ("correct_trace", _answer(["Let the first ship have x people.", "Then the next two ships had 2x and 4x people.", f"x + 2x + 4x = {total}", f"7x = {total}", f"x = {first}"], first), True, first),
            ("arithmetic_error", _answer(["Let the first ship have x people.", "Then the next two ships had 2x and 4x people.", f"x + 2x + 4x = {total}", f"7x = {total}", f"x = {first - 4}"], first - 4), False, first - 4),
            ("relation_error", _answer(["Let the first ship have x people.", "Then the next two ships had 3x and 4x people.", f"x + 3x + 4x = {total}", f"8x = {total}", f"x = {total / 8:g}"], total / 8), False, total / 8),
            ("target_confusion", _answer([f"x + 2x + 4x = {total}", f"7x = {total}", f"x = {first}", f"So the last ship had {third} people."], third), False, third),
            ("final_answer_only", f"I think the answer is {first}.", True, first),
        ]
        return text, float(first), _pack_variants(variants, ["narrative_doubling"])
    raise ValueError(f"Unsupported kind: {k}")


def _pack_variants(variants: list[tuple[str, str, bool, float | None]], notes: list[str]) -> list[dict]:
    return [
        {
            "variant_type": variant_type,
            "student_answer": student_answer,
            "expected_correctness": expected_correctness,
            "expected_student_final_answer": float(expected_value) if expected_value is not None else None,
            "notes": list(notes) + [variant_type],
        }
        for variant_type, student_answer, expected_correctness, expected_value in variants
    ]


SAMPLE_COUNTS = {
    "algebra_variable": 40,
    "unit_rate": 30,
    "percent": 30,
    "compare_sum_difference": 30,
    "intermediate_target": 20,
    "growth_pattern": 20,
    "geometry": 20,
    "hard_parse": 10,
}


def _budgets(problems: list[dict]) -> dict[str, int]:
    grouped: dict[str, list[dict]] = {}
    for problem in problems:
        grouped.setdefault(problem["category"], []).append(problem)
    result: dict[str, int] = {}
    for category, items in grouped.items():
        q, r = divmod(SAMPLE_COUNTS[category], len(items))
        for idx, problem in enumerate(items):
            result[problem["problem_id"]] = q + (1 if idx < r else 0)
    return result


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    problems = build_base_problems()
    base_payload = []
    samples = []
    for problem in problems:
        text, gold, variants = _render(problem)
        base_payload.append(
            {
                "problem_id": problem["problem_id"],
                "category": problem["category"],
                "difficulty": problem["difficulty"],
                "problem_text": text,
                "gold_final_answer": gold,
                "available_variant_types": [variant["variant_type"] for variant in variants],
            }
        )
        problem["rendered_text"] = text
        problem["gold_final_answer"] = gold
        problem["rendered_variants"] = variants

    budgets = _budgets(problems)
    for problem in problems:
        for idx, variant in enumerate(problem["rendered_variants"][: budgets[problem["problem_id"]]], 1):
            samples.append(
                {
                    "sample_id": f"{problem['problem_id']}__{variant['variant_type']}_{idx}",
                    "problem_id": problem["problem_id"],
                    "category": problem["category"],
                    "difficulty": problem["difficulty"],
                    "problem_text": problem["rendered_text"],
                    "gold_final_answer": problem["gold_final_answer"],
                    **variant,
                }
            )

    if len(samples) != 200:
        raise ValueError(f"Expected 200 samples, got {len(samples)}")

    BASE_PATH.write_text(json.dumps(base_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    with SAMPLES_PATH.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
    SUMMARY_PATH.write_text(
        json.dumps(
            {
                "base_problem_count": len(base_payload),
                "sample_count": len(samples),
                "category_counts": {k: sum(1 for sample in samples if sample["category"] == k) for k in SAMPLE_COUNTS},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("Generated benchmark artifacts.")
    print(f"Base problems: {len(base_payload)}")
    print(f"Samples: {len(samples)}")


if __name__ == "__main__":
    main()
