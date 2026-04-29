import pytest

from src.models import (
    CanonicalReference,
    DiagnosisEvidence,
    DiagnosisLabel,
    DiagnosisResult,
    DisclosurePolicy,
    ErrorLocalization,
    ExecutablePlan,
    ExecutableStep,
    ExecutionStepResult,
    ExecutionTrace,
    EvidenceItem,
    FormalizedProblem,
    ProblemGraph,
    ProblemGraphEdge,
    ProblemGraphEdgeType,
    ProblemGraphNode,
    ProblemGraphNodeType,
    HintLevel,
    HintPlan,
    InterventionPosture,
    OperationType,
    PedagogicalObjective,
    PedagogyState,
    ProblemEntity,
    ProvenanceSource,
    QuantityAnnotation,
    QuantitySemanticRole,
    RelationCandidate,
    RelationType,
    StudentStepAttempt,
    StudentWorkMode,
    StudentWorkState,
    StepGroundingRequirement,
    TargetSpec,
    TeacherMove,
    TraceOperation,
)


def _formalized_problem() -> FormalizedProblem:
    return FormalizedProblem(
        problem_text="A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?",
        entities=[
            ProblemEntity(
                entity_id="mr_benson",
                surface_text="Mr. Benson",
                normalized_name="Mr. Benson",
                entity_type="person",
            )
        ],
        quantities=[
            QuantityAnnotation(
                quantity_id="ticket_price",
                surface_text="$40",
                value=40.0,
                unit="dollars",
                semantic_role=QuantitySemanticRole.UNIT_RATE,
                provenance=ProvenanceSource.PROBLEM_TEXT,
            ),
            QuantityAnnotation(
                quantity_id="ticket_count",
                surface_text="12",
                value=12.0,
                unit="tickets",
                entity_id="mr_benson",
                semantic_role=QuantitySemanticRole.BASE,
                provenance=ProvenanceSource.PROBLEM_TEXT,
            ),
            QuantityAnnotation(
                quantity_id="discount_rate",
                surface_text="5%",
                value=5.0,
                unit="percent",
                semantic_role=QuantitySemanticRole.PERCENT,
                provenance=ProvenanceSource.PROBLEM_TEXT,
                is_target_candidate=False,
            ),
        ],
        target=TargetSpec(
            surface_text="How much did Mr. Benson pay in all?",
            target_variable="final_total",
            unit="dollars",
            provenance=ProvenanceSource.PROBLEM_TEXT,
            confidence=0.92,
        ),
        relation_candidates=[
            RelationCandidate(
                relation_id="discount_after_threshold",
                relation_type=RelationType.RATE_UNIT_RELATION,
                operation_hint=OperationType.SUBTRACTIVE,
                source_quantity_ids=["ticket_price", "ticket_count", "discount_rate"],
                target_variable="final_total",
                expression="ticket_count * ticket_price - ((ticket_count - 10) * (discount_rate/100) * ticket_price)",
                confidence=0.84,
                provenance=ProvenanceSource.LLM,
            )
        ],
        problem_graph=ProblemGraph(
            nodes=[
                ProblemGraphNode(
                    node_id="ticket_price",
                    node_type=ProblemGraphNodeType.QUANTITY,
                    label="$40",
                    quantity_id="ticket_price",
                    value=40.0,
                    unit="dollars",
                    semantic_role=QuantitySemanticRole.UNIT_RATE,
                    confidence=0.95,
                    provenance=ProvenanceSource.PROBLEM_TEXT,
                ),
                ProblemGraphNode(
                    node_id="final_total",
                    node_type=ProblemGraphNodeType.TARGET,
                    label="How much did Mr. Benson pay in all?",
                    target_variable="final_total",
                    unit="dollars",
                    confidence=0.9,
                    provenance=ProvenanceSource.PROBLEM_TEXT,
                ),
                ProblemGraphNode(
                    node_id="op_step_1",
                    node_type=ProblemGraphNodeType.OPERATION,
                    label="Compute the final total from the compiled relation.",
                    operation=TraceOperation.DERIVE,
                    expression="ticket_price",
                    step_id="step_1",
                    step_index=1,
                    confidence=0.6,
                    provenance=ProvenanceSource.HEURISTIC,
                ),
            ],
            edges=[
                ProblemGraphEdge(
                    edge_id="edge_ticket_price_to_op_step_1",
                    source_node_id="ticket_price",
                    target_node_id="op_step_1",
                    edge_type=ProblemGraphEdgeType.INPUT_TO_OPERATION,
                    position=0,
                    confidence=0.8,
                    provenance=ProvenanceSource.HEURISTIC,
                ),
                ProblemGraphEdge(
                    edge_id="edge_op_step_1_to_final_total",
                    source_node_id="op_step_1",
                    target_node_id="final_total",
                    edge_type=ProblemGraphEdgeType.OUTPUT_FROM_OPERATION,
                    confidence=0.8,
                    provenance=ProvenanceSource.HEURISTIC,
                ),
            ],
            target_node_id="final_total",
            confidence=0.8,
            provenance=ProvenanceSource.HEURISTIC,
        ),
        assumptions=["discount applies only to tickets beyond the first 10"],
        confidence=0.86,
        provenance=ProvenanceSource.LLM,
        notes=["phase1_schema_test"],
    )


def _executable_plan() -> ExecutablePlan:
    return ExecutablePlan(
        plan_id="plan_a",
        target_ref="final_total",
        steps=[
            ExecutableStep(
                step_id="step_1",
                operation=TraceOperation.SUBTRACT,
                expression="12 - 10",
                input_refs=["ticket_count"],
                output_ref="discounted_ticket_count",
                confidence=0.9,
                provenance=ProvenanceSource.LLM,
            ),
            ExecutableStep(
                step_id="step_2",
                operation=TraceOperation.PERCENT_OF,
                expression="5% of 40",
                input_refs=["discount_rate", "ticket_price"],
                output_ref="discount_per_ticket",
                confidence=0.9,
                provenance=ProvenanceSource.LLM,
            ),
            ExecutableStep(
                step_id="step_3",
                operation=TraceOperation.SUBTRACT,
                expression="480 - 4",
                input_refs=["ticket_count", "ticket_price"],
                output_ref="final_total",
                confidence=0.88,
                provenance=ProvenanceSource.LLM,
            ),
        ],
        confidence=0.89,
        provenance=ProvenanceSource.LLM,
    )


def test_formalized_problem_schema_round_trip():
    problem = _formalized_problem()
    assert problem.target is not None
    assert problem.target.target_variable == "final_total"
    assert problem.quantities[0].semantic_role == QuantitySemanticRole.UNIT_RATE
    assert problem.relation_candidates[0].relation_type == RelationType.RATE_UNIT_RELATION
    assert problem.problem_graph is not None
    assert problem.problem_graph.target_node_id == "final_total"


def test_formalized_problem_rejects_unknown_quantity_reference():
    with pytest.raises(ValueError):
        FormalizedProblem(
            problem_text="A problem",
            quantities=[
                QuantityAnnotation(
                    quantity_id="q1",
                    surface_text="5",
                    value=5.0,
                    provenance=ProvenanceSource.PROBLEM_TEXT,
                )
            ],
            relation_candidates=[
                RelationCandidate(
                    relation_id="r1",
                    relation_type=RelationType.ADDITIVE_COMPOSITION,
                    source_quantity_ids=["q_missing"],
                    confidence=0.5,
                )
            ],
        )


def test_problem_graph_rejects_unknown_edge_reference():
    with pytest.raises(ValueError):
        ProblemGraph(
            nodes=[
                ProblemGraphNode(
                    node_id="q1",
                    node_type=ProblemGraphNodeType.QUANTITY,
                    label="5",
                    quantity_id="q1",
                    value=5.0,
                    confidence=0.9,
                )
            ],
            edges=[
                ProblemGraphEdge(
                    edge_id="edge_bad",
                    source_node_id="q1",
                    target_node_id="missing",
                    edge_type=ProblemGraphEdgeType.INPUT_TO_OPERATION,
                    confidence=0.5,
                )
            ],
            target_node_id="q1",
        )


def test_execution_trace_requires_output_for_success():
    with pytest.raises(ValueError):
        ExecutionStepResult(
            step_id="step_1",
            operation=TraceOperation.ADD,
            resolved_inputs=[1.0, 2.0],
            success=True,
        )


def test_execution_trace_requires_error_for_failure():
    with pytest.raises(ValueError):
        ExecutionStepResult(
            step_id="step_1",
            operation=TraceOperation.ADD,
            resolved_inputs=[1.0, 2.0],
            success=False,
        )


def test_canonical_reference_requires_consistent_final_answer():
    problem = _formalized_problem()
    plan = _executable_plan()
    trace = ExecutionTrace(
        plan_id="plan_a",
        step_results=[
            ExecutionStepResult(
                step_id="step_1",
                operation=TraceOperation.SUBTRACT,
                resolved_inputs=[12.0, 10.0],
                output_value=2.0,
                success=True,
            ),
            ExecutionStepResult(
                step_id="step_2",
                operation=TraceOperation.PERCENT_OF,
                resolved_inputs=[5.0, 40.0],
                output_value=2.0,
                success=True,
            ),
            ExecutionStepResult(
                step_id="step_3",
                operation=TraceOperation.SUBTRACT,
                resolved_inputs=[480.0, 4.0],
                output_value=476.0,
                success=True,
            ),
        ],
        final_value=476.0,
        success=True,
        confidence=0.9,
    )
    reference = CanonicalReference(
        final_answer=476.0,
        formalized_problem=problem,
        chosen_plan=plan,
        execution_trace=trace,
        rendered_solution_text="...",
        source_model="test-model",
        confidence=0.9,
    )
    assert reference.execution_trace.final_value == 476.0


def test_canonical_reference_rejects_mismatched_final_answer():
    problem = _formalized_problem()
    plan = _executable_plan()
    trace = ExecutionTrace(
        plan_id="plan_a",
        step_results=[
            ExecutionStepResult(
                step_id="step_3",
                operation=TraceOperation.SUBTRACT,
                resolved_inputs=[480.0, 4.0],
                output_value=476.0,
                success=True,
            )
        ],
        final_value=476.0,
        success=True,
        confidence=0.9,
    )
    with pytest.raises(ValueError):
        CanonicalReference(
            final_answer=480.0,
            formalized_problem=problem,
            chosen_plan=plan,
            execution_trace=trace,
            confidence=0.9,
        )


def test_student_work_state_supports_partial_trace():
    state = StudentWorkState(
        raw_answer="Step 1 - 12 * 40 = 480\nStep 2 - Answer is 516",
        normalized_final_answer=516.0,
        mode=StudentWorkMode.PARTIAL_TRACE,
        steps=[
            StudentStepAttempt(
                step_id="student_1",
                raw_text="12 * 40 = 480",
                operation=TraceOperation.MULTIPLY,
                extracted_value=480.0,
                confidence=0.75,
            )
        ],
        confidence=0.66,
    )
    assert state.mode == StudentWorkMode.PARTIAL_TRACE
    assert state.steps[0].operation == TraceOperation.MULTIPLY


def test_student_work_state_rejects_duplicate_step_ids():
    with pytest.raises(ValueError):
        StudentWorkState(
            raw_answer="work",
            steps=[
                StudentStepAttempt(step_id="s1", raw_text="first"),
                StudentStepAttempt(step_id="s1", raw_text="second"),
            ],
        )


def test_diagnosis_evidence_and_hint_plan_schema():
    evidence = DiagnosisEvidence(
        evidence_items=[
            EvidenceItem(
                evidence_type="intermediate_quantity_selected",
                description="Student stopped at a non-target intermediate value.",
                confidence=0.83,
                reference_step_id="step_1",
                quantity_ids=["discounted_ticket_count"],
            )
        ],
        first_divergence_step_id="step_1",
        likely_error_mechanisms=["stopped_at_intermediate_quantity"],
        confidence=0.81,
    )
    plan = HintPlan(
        diagnosis_label=DiagnosisLabel.TARGET_MISUNDERSTANDING,
        hint_level=HintLevel.CONCEPTUAL,
        teacher_move=TeacherMove.REFOCUS_TARGET,
        target_step_id="step_1",
        disclosure_budget=1,
        focus_points=["what quantity the question asks for"],
        must_not_reveal=["final answer", "intermediate numeric target"],
        rationale="Student appears to have solved for an intermediate quantity.",
        confidence=0.84,
    )
    assert evidence.first_divergence_step_id == "step_1"
    assert plan.teacher_move == TeacherMove.REFOCUS_TARGET


def test_diagnosis_result_requires_non_empty_summary():
    result = DiagnosisResult(
        diagnosis_label=DiagnosisLabel.ARITHMETIC_ERROR,
        subtype="final_computation_error",
        localization=ErrorLocalization.FINAL_COMPUTATION,
        summary="Student reached the right target but computed the wrong value.",
        confidence=0.8,
    )
    assert result.localization == ErrorLocalization.FINAL_COMPUTATION


def test_hint_plan_rejects_focus_points_when_budget_is_zero():
    with pytest.raises(ValueError):
        HintPlan(
            diagnosis_label=DiagnosisLabel.UNKNOWN_ERROR,
            hint_level=HintLevel.CONCEPTUAL,
            teacher_move=TeacherMove.METACOGNITIVE_PROMPT,
            disclosure_budget=0,
            focus_points=["something"],
            rationale="none",
        )


def test_pedagogy_state_accepts_common_typo_alias_for_uncertain_concerns():
    state = PedagogyState.model_validate(
        {
            "intervention_posture": InterventionPosture.CORRECTIVE.value,
            "primary_objective": PedagogicalObjective.REFOCUS_TARGET.value,
            "disclosure_policy": DisclosurePolicy.LOW.value,
            "step_grounding_requirement": StepGroundingRequirement.OPTIONAL.value,
            "uncertain_pedagogical_conerns": ["student may be tracking the wrong quantity"],
            "pedagogical_goal": "Refocus the student on the requested quantity.",
            "student_action": "Re-identify what the question asks for.",
            "rationale": "The student appears to stop at an intermediate quantity.",
            "confidence": 0.8,
            "notes": ["schema_alias_test"],
        }
    )

    assert state.uncertain_pedagogical_concerns == ["student may be tracking the wrong quantity"]
