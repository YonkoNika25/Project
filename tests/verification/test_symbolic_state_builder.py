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
