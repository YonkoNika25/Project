from src.models import OperationType
from src.verification.symbolic_state_builder import build_symbolic_state


def test_build_symbolic_state_additive_problem():
    problem = "Jan has 3 apples. She buys 5 more apples. How many apples does she have in total?"
    state = build_symbolic_state(problem)
    assert state.expected_operation == OperationType.ADDITIVE
    assert [q.value for q in state.quantities] == [3.0, 5.0]
    assert state.builder_confidence > 0.5


def test_build_symbolic_state_subtractive_problem():
    problem = "Tom had 10 marbles and gave away 4. How many marbles are left?"
    state = build_symbolic_state(problem)
    assert state.expected_operation == OperationType.SUBTRACTIVE
    assert [q.value for q in state.quantities] == [10.0, 4.0]


def test_build_symbolic_state_extracts_question_target_only():
    problem = (
        "Julie is reading a 120-page book. Yesterday, she was able to read 12 pages "
        "and today, she read twice as many pages as yesterday. "
        "If she wants to read half of the remaining pages tomorrow, how many pages should she read?"
    )
    state = build_symbolic_state(problem)
    assert state.target_text == "If she wants to read half of the remaining pages tomorrow, how many pages should she read?"


def test_build_symbolic_state_handles_abbreviation_in_question():
    problem = (
        "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount "
        "for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?"
    )
    state = build_symbolic_state(problem)
    assert state.target_text == "How much did Mr. Benson pay in all?"


def test_build_symbolic_state_marks_unsupported_relation_cues_when_operation_is_unclear():
    problem = "There are 7 boxes with 3 apples in each box. How many apples are there?"
    state = build_symbolic_state(problem)
    assert state.expected_operation == OperationType.UNKNOWN
    assert any(note.startswith("unsupported_relation_cues=") for note in state.evidence_notes)


def test_build_symbolic_state_records_operation_cues_in_notes():
    problem = "Tom had 10 marbles and gave away 4. How many marbles are left?"
    state = build_symbolic_state(problem)
    assert any(note.startswith("subtractive_cues=") for note in state.evidence_notes)
    assert "target_question_extracted" in state.evidence_notes


def test_build_symbolic_state_handles_still_available_as_subtractive_cue():
    problem = "Mary has 5 green crayons and 8 blue crayons. If she gives out 3 crayons, how many crayons does she have still available?"
    state = build_symbolic_state(problem)
    assert state.expected_operation == OperationType.SUBTRACTIVE
    assert any("still available" in note for note in state.evidence_notes if note.startswith("subtractive_cues="))
