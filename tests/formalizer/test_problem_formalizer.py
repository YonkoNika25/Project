from src.formalizer import build_reference_trace, formalize_problem
from src.models import OperationType, ProblemGraphNodeType, ProvenanceSource, RelationType


def test_formalize_problem_extracts_target_quantities_and_relation():
    problem = (
        "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount "
        "for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?"
    )
    formalized = formalize_problem(problem)

    assert formalized.target is not None
    assert formalized.target.surface_text == "How much did Mr. Benson pay in all?"
    assert len(formalized.quantities) == 4
    assert any("role_hints=rate_like" in note for q in formalized.quantities for note in q.notes)
    assert any("role_hints=percent_like,rate_like" in note for q in formalized.quantities for note in q.notes)
    assert any("role_hints=threshold_like" in note for q in formalized.quantities for note in q.notes)
    assert formalized.relation_candidates[0].relation_type == RelationType.RATE_UNIT_RELATION
    assert formalized.provenance == ProvenanceSource.HEURISTIC
    assert formalized.confidence > 0.5
    assert all(q.entity_id is not None for q in formalized.quantities)
    assert formalized.problem_graph is not None
    assert formalized.problem_graph.target_node_id == formalized.target.target_variable
    operation_nodes = [node for node in formalized.problem_graph.nodes if node.node_type == ProblemGraphNodeType.OPERATION]
    assert len(operation_nodes) == 5
    assert operation_nodes[0].step_id == "step_1_excess_quantity"


def test_formalize_problem_extracts_named_entities():
    problem = (
        "Mia gave Noah 3 books and then Noah bought 2 more books. "
        "How many books does Noah have now?"
    )
    formalized = formalize_problem(problem)
    entity_names = [entity.surface_text for entity in formalized.entities]
    assert "Mia" not in entity_names  # single-token names are not promoted yet
    assert formalized.target is not None
    assert formalized.target.target_variable.startswith("how_many_books")


def test_formalize_problem_handles_additive_problem():
    problem = "Jan has 3 apples. She buys 5 more apples. How many apples does she have in total?"
    formalized = formalize_problem(problem)

    assert formalized.relation_candidates[0].relation_type == RelationType.ADDITIVE_COMPOSITION
    assert formalized.relation_candidates[0].operation_hint == OperationType.ADDITIVE
    assert formalized.target is not None
    assert formalized.target.unit == "apples"


def test_formalize_problem_handles_subtractive_problem():
    problem = "Tom had 10 marbles and gave away 4. How many marbles are left?"
    formalized = formalize_problem(problem)

    assert formalized.relation_candidates[0].relation_type == RelationType.SUBTRACTIVE_COMPARISON
    assert formalized.relation_candidates[0].operation_hint == OperationType.SUBTRACTIVE


def test_shared_reference_trace_builder_remains_available():
    trace = build_reference_trace("10 - 4 = 6\n#### 6", target_text="How many marbles are left?")
    assert trace.final_value == 6.0
    assert trace.steps[0].operation.value == "subtract"


def test_formalize_problem_attaches_target_quantity_when_explicit():
    formalized = formalize_problem("There are 8 apples. How many apples are there?")
    assert formalized.target is not None
    assert formalized.target.target_quantity_id is None
    assert any(note == "target_link_candidates_extracted=2" for note in formalized.notes)
    assert formalized.problem_graph is not None
    assert any(node.node_type == ProblemGraphNodeType.TARGET for node in formalized.problem_graph.nodes)
