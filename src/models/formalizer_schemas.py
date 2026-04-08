from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.schemas import (
    DiagnosisLabel,
    ErrorLocalization,
    HintLevel,
    HintMode,
    OperationType,
    ProvenanceSource,
    RelationType,
    TraceOperation,
)


class QuantitySemanticRole(str, Enum):
    BASE = "base"
    RATE = "rate"
    UNIT_RATE = "unit_rate"
    PERCENT = "percent"
    THRESHOLD = "threshold"
    INTERMEDIATE = "intermediate"
    TARGET_CANDIDATE = "target_candidate"
    UNKNOWN = "unknown"


class StudentWorkMode(str, Enum):
    FINAL_ANSWER_ONLY = "final_answer_only"
    PARTIAL_TRACE = "partial_trace"
    FULL_TRACE = "full_trace"
    UNPARSEABLE = "unparseable"


class TeacherMove(str, Enum):
    REFOCUS_TARGET = "refocus_target"
    CHECK_RELATIONSHIP = "check_relationship"
    RECOMPUTE_STEP = "recompute_step"
    CONTINUE_FROM_STEP = "continue_from_step"
    RESTATE_RESULT = "restate_result"
    METACOGNITIVE_PROMPT = "metacognitive_prompt"


class ProblemGraphNodeType(str, Enum):
    ENTITY = "entity"
    QUANTITY = "quantity"
    OPERATION = "operation"
    INTERMEDIATE = "intermediate"
    TARGET = "target"


class ProblemGraphEdgeType(str, Enum):
    ENTITY_HAS_QUANTITY = "entity_has_quantity"
    TARGETS_VALUE = "targets_value"
    DESCRIBES_ENTITY = "describes_entity"
    INPUT_TO_OPERATION = "input_to_operation"
    OUTPUT_FROM_OPERATION = "output_from_operation"


class ProblemEntity(BaseModel):
    entity_id: str = Field(description="Stable identifier for an entity in the problem")
    surface_text: str = Field(description="Original text span for the entity")
    normalized_name: Optional[str] = Field(default=None, description="Canonical entity name if normalized")
    entity_type: str = Field(default="unknown", description="Lightweight entity category")
    aliases: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_entity_id(self):
        if not self.entity_id.strip():
            raise ValueError("entity_id must not be empty")
        return self


class QuantityAnnotation(BaseModel):
    quantity_id: str = Field(description="Stable quantity identifier")
    surface_text: str = Field(description="Original quantity text span")
    value: float = Field(description="Normalized numeric value")
    unit: Optional[str] = Field(default=None)
    entity_id: Optional[str] = Field(default=None)
    semantic_role: QuantitySemanticRole = Field(default=QuantitySemanticRole.UNKNOWN)
    sentence_index: Optional[int] = Field(default=None, ge=0)
    char_start: Optional[int] = Field(default=None, ge=0)
    char_end: Optional[int] = Field(default=None, ge=0)
    is_target_candidate: bool = Field(default=False)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_char_span(self):
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must be >= char_start")
        if not self.quantity_id.strip():
            raise ValueError("quantity_id must not be empty")
        return self


class TargetSpec(BaseModel):
    surface_text: str
    normalized_question: Optional[str] = Field(default=None)
    target_variable: str = Field(description="Symbolic variable name for the target")
    target_quantity_id: Optional[str] = Field(default=None)
    entity_id: Optional[str] = Field(default=None)
    unit: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_target_variable(self):
        if not self.target_variable.strip():
            raise ValueError("target_variable must not be empty")
        return self


class RelationCandidate(BaseModel):
    relation_id: str
    relation_type: RelationType = Field(default=RelationType.UNKNOWN)
    operation_hint: OperationType = Field(default=OperationType.UNKNOWN)
    source_quantity_ids: List[str] = Field(default_factory=list)
    target_variable: Optional[str] = Field(default=None)
    expression: Optional[str] = Field(default=None, description="Lightweight symbolic expression")
    rationale: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_relation_id(self):
        if not self.relation_id.strip():
            raise ValueError("relation_id must not be empty")
        return self


class ProblemGraphNode(BaseModel):
    node_id: str
    node_type: ProblemGraphNodeType
    label: str
    value: Optional[float] = Field(default=None)
    unit: Optional[str] = Field(default=None)
    quantity_id: Optional[str] = Field(default=None)
    entity_id: Optional[str] = Field(default=None)
    target_variable: Optional[str] = Field(default=None)
    semantic_role: Optional[QuantitySemanticRole] = Field(default=None)
    operation: Optional[TraceOperation] = Field(default=None)
    expression: Optional[str] = Field(default=None)
    step_id: Optional[str] = Field(default=None)
    step_index: Optional[int] = Field(default=None, ge=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_node_shape(self):
        if not self.node_id.strip():
            raise ValueError("node_id must not be empty")
        if self.node_type == ProblemGraphNodeType.OPERATION:
            if self.operation is None:
                raise ValueError("Operation graph nodes must include an operation")
            if self.expression is None or not self.expression.strip():
                raise ValueError("Operation graph nodes must include an expression")
            if self.step_id is None or not self.step_id.strip():
                raise ValueError("Operation graph nodes must include a step_id")
            if self.step_index is None:
                raise ValueError("Operation graph nodes must include a step_index")
        return self


class ProblemGraphEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: ProblemGraphEdgeType
    position: Optional[int] = Field(default=None, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_edge_shape(self):
        if not self.edge_id.strip():
            raise ValueError("edge_id must not be empty")
        if not self.source_node_id.strip():
            raise ValueError("source_node_id must not be empty")
        if not self.target_node_id.strip():
            raise ValueError("target_node_id must not be empty")
        return self


class ProblemGraph(BaseModel):
    nodes: List[ProblemGraphNode] = Field(default_factory=list)
    edges: List[ProblemGraphEdge] = Field(default_factory=list)
    target_node_id: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_graph_references(self):
        node_ids = [node.node_id for node in self.nodes]
        edge_ids = [edge.edge_id for edge in self.edges]

        if len(node_ids) != len(set(node_ids)):
            raise ValueError("ProblemGraph contains duplicate node_id values")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("ProblemGraph contains duplicate edge_id values")

        if self.target_node_id is not None and self.target_node_id not in node_ids:
            raise ValueError(f"ProblemGraph.target_node_id '{self.target_node_id}' does not exist in nodes")

        for edge in self.edges:
            if edge.source_node_id not in node_ids:
                raise ValueError(f"ProblemGraphEdge source '{edge.source_node_id}' does not exist in nodes")
            if edge.target_node_id not in node_ids:
                raise ValueError(f"ProblemGraphEdge target '{edge.target_node_id}' does not exist in nodes")

        return self


class FormalizedProblem(BaseModel):
    problem_text: str
    quantities: List[QuantityAnnotation] = Field(default_factory=list)
    entities: List[ProblemEntity] = Field(default_factory=list)
    target: Optional[TargetSpec] = Field(default=None)
    relation_candidates: List[RelationCandidate] = Field(default_factory=list)
    problem_graph: Optional[ProblemGraph] = Field(default=None)
    assumptions: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_internal_references(self):
        quantity_ids = [quantity.quantity_id for quantity in self.quantities]
        entity_ids = [entity.entity_id for entity in self.entities]

        if len(quantity_ids) != len(set(quantity_ids)):
            raise ValueError("FormalizedProblem contains duplicate quantity_id values")
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("FormalizedProblem contains duplicate entity_id values")

        for quantity in self.quantities:
            if quantity.entity_id is not None and quantity.entity_id not in entity_ids:
                raise ValueError(f"QuantityAnnotation.entity_id '{quantity.entity_id}' does not exist in entities")

        if self.target is not None:
            if self.target.target_quantity_id is not None and self.target.target_quantity_id not in quantity_ids:
                raise ValueError(
                    f"TargetSpec.target_quantity_id '{self.target.target_quantity_id}' does not exist in quantities"
                )
            if self.target.entity_id is not None and self.target.entity_id not in entity_ids:
                raise ValueError(f"TargetSpec.entity_id '{self.target.entity_id}' does not exist in entities")

        relation_ids = [relation.relation_id for relation in self.relation_candidates]
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("FormalizedProblem contains duplicate relation_id values")

        for relation in self.relation_candidates:
            unknown_refs = [ref for ref in relation.source_quantity_ids if ref not in quantity_ids]
            if unknown_refs:
                raise ValueError(
                    f"RelationCandidate '{relation.relation_id}' references unknown quantities: {unknown_refs}"
                )
            if relation.target_variable is not None and not relation.target_variable.strip():
                raise ValueError("RelationCandidate.target_variable must not be empty when provided")

        if self.problem_graph is not None:
            if self.target is not None and self.problem_graph.target_node_id is not None:
                if self.problem_graph.target_node_id != self.target.target_variable:
                    raise ValueError("ProblemGraph.target_node_id must match TargetSpec.target_variable")

            for node in self.problem_graph.nodes:
                if node.quantity_id is not None and node.quantity_id not in quantity_ids:
                    raise ValueError(f"ProblemGraph node '{node.node_id}' references unknown quantity_id '{node.quantity_id}'")
                if node.entity_id is not None and node.entity_id not in entity_ids:
                    raise ValueError(f"ProblemGraph node '{node.node_id}' references unknown entity_id '{node.entity_id}'")

        return self


class ExecutableStep(BaseModel):
    step_id: str
    operation: TraceOperation = Field(default=TraceOperation.UNKNOWN)
    expression: str = Field(description="Executable symbolic expression or normalized formula")
    input_refs: List[str] = Field(default_factory=list, description="Quantity ids or variable refs")
    output_ref: str = Field(description="Variable name produced by this step")
    explanation: Optional[str] = Field(default=None)
    executable_code: Optional[str] = Field(default=None, description="Optional Python snippet or executable code")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_step_ids(self):
        if not self.step_id.strip():
            raise ValueError("step_id must not be empty")
        if not self.output_ref.strip():
            raise ValueError("output_ref must not be empty")
        return self


class ExecutablePlan(BaseModel):
    plan_id: str
    target_ref: str
    steps: List[ExecutableStep] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_plan_structure(self):
        if not self.plan_id.strip():
            raise ValueError("plan_id must not be empty")
        if not self.target_ref.strip():
            raise ValueError("target_ref must not be empty")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("ExecutablePlan contains duplicate step_id values")
        return self


class ExecutionStepResult(BaseModel):
    step_id: str
    operation: TraceOperation = Field(default=TraceOperation.UNKNOWN)
    resolved_inputs: List[float] = Field(default_factory=list)
    output_value: Optional[float] = Field(default=None)
    success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_output_on_success(self):
        if self.success and self.output_value is None:
            raise ValueError("Successful execution step must include output_value")
        if not self.success and not self.error_message:
            raise ValueError("Failed execution step must include error_message")
        return self


class ExecutionTrace(BaseModel):
    plan_id: str
    step_results: List[ExecutionStepResult] = Field(default_factory=list)
    final_value: Optional[float] = Field(default=None)
    success: bool = Field(default=False)
    error_message: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_final_value_on_success(self):
        if self.success and self.final_value is None:
            raise ValueError("Successful execution trace must include final_value")
        return self


class SolverCandidate(BaseModel):
    candidate_id: str
    executable_plan: ExecutablePlan
    rendered_reasoning: Optional[str] = Field(default=None)
    selection_score: float = Field(default=0.0)
    selection_notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_candidate_id(self):
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        return self


class CanonicalReference(BaseModel):
    final_answer: float
    formalized_problem: FormalizedProblem
    chosen_plan: ExecutablePlan
    execution_trace: ExecutionTrace
    rendered_solution_text: Optional[str] = Field(default=None)
    source_model: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_reference_consistency(self):
        if self.execution_trace.success and self.execution_trace.final_value is not None:
            if abs(self.execution_trace.final_value - self.final_answer) > 1e-9:
                raise ValueError("CanonicalReference final_answer must match successful execution_trace.final_value")
        return self


class StudentStepAttempt(BaseModel):
    step_id: str
    raw_text: str
    operation: Optional[TraceOperation] = Field(default=None)
    input_values: List[float] = Field(default_factory=list)
    extracted_value: Optional[float] = Field(default=None)
    referenced_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_step_attempt_id(self):
        if not self.step_id.strip():
            raise ValueError("step_id must not be empty")
        return self


class StudentSemanticFact(BaseModel):
    fact_id: str
    label: str
    value: Optional[float] = Field(default=None)
    grounding: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_fact_id(self):
        if not self.fact_id.strip():
            raise ValueError("fact_id must not be empty")
        if not self.label.strip():
            raise ValueError("label must not be empty")
        return self


class StudentWorkState(BaseModel):
    raw_answer: str
    normalized_final_answer: Optional[float] = Field(default=None)
    mode: StudentWorkMode = Field(default=StudentWorkMode.FINAL_ANSWER_ONLY)
    semantic_facts: List[StudentSemanticFact] = Field(default_factory=list)
    steps: List[StudentStepAttempt] = Field(default_factory=list)
    student_graph: Optional[ProblemGraph] = Field(default=None)
    selected_target_ref: Optional[str] = Field(default=None)
    assumptions: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_student_step_uniqueness(self):
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("StudentWorkState contains duplicate step_id values")
        fact_ids = [fact.fact_id for fact in self.semantic_facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("StudentWorkState contains duplicate semantic fact ids")
        if self.student_graph is not None and self.student_graph.target_node_id is None and (
            self.normalized_final_answer is not None or self.steps
        ):
            raise ValueError("StudentWorkState.student_graph must include target_node_id when populated")
        return self


class EvidenceItem(BaseModel):
    evidence_type: str
    description: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reference_step_id: Optional[str] = Field(default=None)
    student_step_id: Optional[str] = Field(default=None)
    quantity_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_evidence_type(self):
        if not self.evidence_type.strip():
            raise ValueError("evidence_type must not be empty")
        return self


class DiagnosisEvidence(BaseModel):
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    alignment_map: List[Dict[str, Any]] = Field(default_factory=list)
    first_divergence_step_id: Optional[str] = Field(default=None)
    likely_error_mechanisms: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class GraphValidationIssue(BaseModel):
    code: str
    message: str
    node_id: Optional[str] = Field(default=None)
    edge_id: Optional[str] = Field(default=None)
    step_id: Optional[str] = Field(default=None)
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_issue_code(self):
        if not self.code.strip():
            raise ValueError("code must not be empty")
        if not self.message.strip():
            raise ValueError("message must not be empty")
        return self


class GraphValidationResult(BaseModel):
    is_valid: bool = Field(default=False)
    issues: List[GraphValidationIssue] = Field(default_factory=list)
    target_node_id: Optional[str] = Field(default=None)
    operation_node_count: int = Field(default=0, ge=0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DiagnosisResult(BaseModel):
    diagnosis_label: DiagnosisLabel
    subtype: Optional[str] = Field(default=None)
    localization: ErrorLocalization = Field(default=ErrorLocalization.UNKNOWN)
    target_step_id: Optional[str] = Field(default=None)
    summary: str = Field(default="")
    supporting_evidence_types: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_summary(self):
        if not self.summary.strip():
            raise ValueError("summary must not be empty")
        return self


class HintPlan(BaseModel):
    diagnosis_label: DiagnosisLabel
    hint_level: HintLevel
    teacher_move: TeacherMove
    target_step_id: Optional[str] = Field(default=None)
    disclosure_budget: int = Field(default=1, ge=0, le=5)
    focus_points: List[str] = Field(default_factory=list)
    must_not_reveal: List[str] = Field(default_factory=list)
    rationale: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_focus_points(self):
        if self.disclosure_budget == 0 and self.focus_points:
            raise ValueError("focus_points should be empty when disclosure_budget is 0")
        return self


class HintResult(BaseModel):
    hint_text: str
    hint_level: HintLevel
    hint_mode: HintMode = Field(default=HintMode.NORMAL)
    verification_passed: bool = Field(default=False)
    violated_rules: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_hint_text(self):
        if not self.hint_text.strip():
            raise ValueError("hint_text must not be empty")
        return self


class TutoringResult(BaseModel):
    problem: FormalizedProblem
    reference: CanonicalReference
    student_work: StudentWorkState
    evidence: DiagnosisEvidence
    diagnosis: DiagnosisResult
    hint_plan: HintPlan
    hint_result: HintResult

    model_config = ConfigDict(extra="forbid")
