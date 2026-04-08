from src.formalizer import formalize_problem, formalize_student_work
from src.models import StudentWorkMode, TraceOperation
from src.runtime import solve_problem


def test_student_work_formalizer_handles_final_answer_only():
    problem = formalize_problem(
        "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount "
        "for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?"
    )
    reference = solve_problem(problem.problem_text)

    student = formalize_student_work("Answer is 516.", problem=problem, reference=reference)

    assert student.normalized_final_answer == 516.0
    assert student.mode == StudentWorkMode.FINAL_ANSWER_ONLY
    assert student.steps == []
    assert student.selected_target_ref is None
    assert student.student_graph is not None
    assert student.student_graph.target_node_id == "student_final_answer"
    final_node = next(node for node in student.student_graph.nodes if node.node_id == "student_final_answer")
    assert final_node.value == 516.0


def test_student_work_formalizer_builds_partial_trace_and_maps_reference_ids():
    problem = formalize_problem(
        "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount "
        "for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?"
    )
    reference = solve_problem(problem.problem_text)
    raw_answer = "12 * 40 = 480\n480 - 4 = 476\nAnswer is 476."

    student = formalize_student_work(raw_answer, problem=problem, reference=reference)

    assert student.mode == StudentWorkMode.PARTIAL_TRACE
    assert student.normalized_final_answer == 476.0
    assert student.selected_target_ref is None
    assert len(student.steps) == 3
    assert student.steps[0].operation == TraceOperation.MULTIPLY
    assert "quantity_1" in student.steps[0].referenced_ids
    assert "quantity_2" in student.steps[0].referenced_ids
    assert student.student_graph is not None
    assert student.student_graph.target_node_id == "student_final_answer"
    graph_node_ids = {node.node_id for node in student.student_graph.nodes}
    assert "student_op_student_step_1" in graph_node_ids
    assert "student_output_student_step_2" in graph_node_ids


def test_student_work_formalizer_detects_intermediate_target_selection():
    problem = formalize_problem(
        "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount "
        "for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?"
    )
    reference = solve_problem(problem.problem_text)

    student = formalize_student_work("12 - 10 = 2\nAnswer is 2.", problem=problem, reference=reference)

    assert student.mode == StudentWorkMode.PARTIAL_TRACE
    assert student.selected_target_ref is None
    assert student.student_graph is not None
    final_node = next(node for node in student.student_graph.nodes if node.node_id == "student_final_answer")
    assert final_node.value == 2.0


def test_student_work_formalizer_splits_punctuation_without_spaces():
    problem = formalize_problem(
        "A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. "
        "Over three hundred years, it has consumed 847 people. Ships have been built larger over time, so each new "
        "ship has twice as many people as the last ship. How many people were on the ship the monster ate in the first hundred years?"
    )

    student = formalize_student_work(
        "Let the first ship have x people.Then the next two ships had 2x and 4x people.x + 2x + 4x = 847. 7x = 847. x = 847/7. x = 117.Answer is 117.",
        problem=problem,
    )

    assert student.mode == StudentWorkMode.PARTIAL_TRACE
    assert len(student.steps) >= 4
    assert student.steps[0].raw_text.startswith("Let the first ship have x people.")
    assert student.steps[1].raw_text.startswith("Then the next two ships had 2x and 4x people.")


def test_student_work_formalizer_marks_unparseable_answers():
    student = formalize_student_work("I do not know.")

    assert student.mode == StudentWorkMode.UNPARSEABLE
    assert student.normalized_final_answer is None
    assert "student_work_unparseable" in student.notes
    assert student.student_graph is None
