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
    """Vai trò ngữ nghĩa thô của một đại lượng trong đề bài."""
    BASE = "base"
    RATE = "rate"
    UNIT_RATE = "unit_rate"
    PERCENT = "percent"
    THRESHOLD = "threshold"
    INTERMEDIATE = "intermediate"
    TARGET_CANDIDATE = "target_candidate"
    UNKNOWN = "unknown"


class StudentWorkMode(str, Enum):
    """Mức độ hệ thống hiểu được bài làm của học sinh."""
    FINAL_ANSWER_ONLY = "final_answer_only"
    PARTIAL_TRACE = "partial_trace"
    FULL_TRACE = "full_trace"
    UNPARSEABLE = "unparseable"


class TeacherMove(str, Enum):
    """Loại động tác sư phạm mà hệ thống muốn dùng khi ra hint."""
    REFOCUS_TARGET = "refocus_target"
    CHECK_RELATIONSHIP = "check_relationship"
    RECOMPUTE_STEP = "recompute_step"
    CONTINUE_FROM_STEP = "continue_from_step"
    RESTATE_RESULT = "restate_result"
    METACOGNITIVE_PROMPT = "metacognitive_prompt"


class ProblemGraphNodeType(str, Enum):
    """Loại node trong đồ thị bài toán/problem_graph."""
    ENTITY = "entity"
    QUANTITY = "quantity"
    OPERATION = "operation"
    INTERMEDIATE = "intermediate"
    TARGET = "target"


class ProblemGraphEdgeType(str, Enum):
    """Loại cạnh trong đồ thị bài toán/problem_graph."""
    ENTITY_HAS_QUANTITY = "entity_has_quantity"
    TARGETS_VALUE = "targets_value"
    DESCRIBES_ENTITY = "describes_entity"
    INPUT_TO_OPERATION = "input_to_operation"
    OUTPUT_FROM_OPERATION = "output_from_operation"


class ProblemEntity(BaseModel):
    """Một thực thể (entity) xuất hiện trong đề bài, ví dụ người, vật, nhóm, nơi chốn."""
    # Mã định danh ổn định của entity trong bài toán.
    entity_id: str = Field(description="Stable identifier for an entity in the problem")
    # Đoạn text gốc trong đề bài dùng để nhận diện entity này.
    surface_text: str = Field(description="Original text span for the entity")
    # Tên chuẩn hóa nếu hệ thống rút được một tên canonical.
    normalized_name: Optional[str] = Field(default=None, description="Canonical entity name if normalized")
    # Loại entity nhẹ, ví dụ person/object/group..., nếu chưa biết thì unknown.
    entity_type: str = Field(default="unknown", description="Lightweight entity category")
    # Các cách gọi khác của cùng entity nếu có.
    aliases: List[str] = Field(default_factory=list)
    # Metadata mở rộng, dùng khi cần giữ thêm thông tin phụ.
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_entity_id(self):
        if not self.entity_id.strip():
            raise ValueError("entity_id must not be empty")
        return self


class QuantityAnnotation(BaseModel):
    """Một đại lượng nhìn thấy trong đề bài sau khi đã được trích và chuẩn hóa."""
    # Mã định danh ổn định của quantity trong bài toán, ví dụ quantity_1.
    quantity_id: str = Field(description="Stable quantity identifier")
    # Đoạn text gốc của số/lượng này trong đề.
    surface_text: str = Field(description="Original quantity text span")
    # Giá trị số đã chuẩn hóa sang float.
    value: float = Field(description="Normalized numeric value")
    # Đơn vị của quantity nếu heuristic/LLM xác định được, ví dụ people, dollars.
    unit: Optional[str] = Field(default=None)
    # Entity mà quantity này gắn với, nếu có.
    entity_id: Optional[str] = Field(default=None)
    # Vai trò ngữ nghĩa thô của quantity này trong bài.
    semantic_role: QuantitySemanticRole = Field(default=QuantitySemanticRole.UNKNOWN)
    # Chỉ số câu mà quantity xuất hiện.
    sentence_index: Optional[int] = Field(default=None, ge=0)
    # Vị trí bắt đầu của quantity trong chuỗi problem_text.
    char_start: Optional[int] = Field(default=None, ge=0)
    # Vị trí kết thúc của quantity trong chuỗi problem_text.
    char_end: Optional[int] = Field(default=None, ge=0)
    # Heuristic đánh dấu đây có thể là quantity đích cần tìm.
    is_target_candidate: bool = Field(default=False)
    # Quantity này đến từ nguồn nào: heuristic, llm, problem_text...
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    # Ghi chú phụ để debug hoặc giữ hint giải thích.
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
    """Đặc tả đại lượng đích mà đề bài đang hỏi."""
    # Câu hỏi hoặc span text gốc mô tả target.
    surface_text: str
    # Câu hỏi đã chuẩn hóa lại nếu có.
    normalized_question: Optional[str] = Field(default=None)
    # Tên biến tượng trưng cho target trong pipeline nội bộ.
    target_variable: str = Field(description="Symbolic variable name for the target")
    # Nếu target trỏ trực tiếp tới một quantity đã biết thì lưu quantity_id ở đây.
    target_quantity_id: Optional[str] = Field(default=None)
    # Entity liên quan tới target, nếu có.
    entity_id: Optional[str] = Field(default=None)
    # Đơn vị của target.
    unit: Optional[str] = Field(default=None)
    # Mô tả ngắn của target.
    description: Optional[str] = Field(default=None)
    # Target này đến từ heuristic hay llm hay nguồn khác.
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    # Độ tin cậy của target spec.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_target_variable(self):
        if not self.target_variable.strip():
            raise ValueError("target_variable must not be empty")
        return self


class RelationCandidate(BaseModel):
    """Một giả thuyết quan hệ toán học giữa các quantity trong đề bài."""
    # Mã định danh của relation candidate.
    relation_id: str
    # Loại quan hệ lớn, ví dụ additive/multiplicative/rate...
    relation_type: RelationType = Field(default=RelationType.UNKNOWN)
    # Gợi ý phép toán thô đi kèm relation này.
    operation_hint: OperationType = Field(default=OperationType.UNKNOWN)
    # Các quantity nguồn tham gia vào relation này.
    source_quantity_ids: List[str] = Field(default_factory=list)
    # Target variable mà relation này muốn tạo ra.
    target_variable: Optional[str] = Field(default=None)
    # Biểu thức symbolic nhẹ dùng để mô tả relation.
    expression: Optional[str] = Field(default=None, description="Lightweight symbolic expression")
    # Giải thích ngắn vì sao relation này được tạo.
    rationale: Optional[str] = Field(default=None)
    # Độ tin cậy của relation candidate.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Nguồn tạo ra relation candidate này.
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_relation_id(self):
        if not self.relation_id.strip():
            raise ValueError("relation_id must not be empty")
        return self


class ProblemGraphNode(BaseModel):
    """Một node trong problem_graph - đồ thị biểu diễn cấu trúc lời giải của đề bài."""
    # Mã node duy nhất trong graph.
    node_id: str
    # Loại node: entity, quantity, operation, intermediate, target.
    node_type: ProblemGraphNodeType
    # Nhãn hiển thị của node.
    label: str
    # Giá trị số nếu node này mang giá trị cụ thể.
    value: Optional[float] = Field(default=None)
    # Đơn vị của node nếu có.
    unit: Optional[str] = Field(default=None)
    # Liên kết về quantity gốc nếu node này đại diện cho quantity nào đó.
    quantity_id: Optional[str] = Field(default=None)
    # Liên kết về entity gốc nếu node này gắn với entity nào đó.
    entity_id: Optional[str] = Field(default=None)
    # Nếu là target node thì target_variable tương ứng.
    target_variable: Optional[str] = Field(default=None)
    # Vai trò semantic nếu node là quantity/intermediate.
    semantic_role: Optional[QuantitySemanticRole] = Field(default=None)
    # Nếu là operation node thì đây là phép toán của bước đó.
    operation: Optional[TraceOperation] = Field(default=None)
    # Biểu thức của operation node.
    expression: Optional[str] = Field(default=None)
    # Step id mà operation node này đại diện.
    step_id: Optional[str] = Field(default=None)
    # Thứ tự bước trong graph nếu là operation node.
    step_index: Optional[int] = Field(default=None, ge=1)
    # Độ tin cậy của node.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Nguồn tạo node.
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    # Ghi chú phụ.
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
    """Một cạnh trong problem_graph, nối các node với nhau theo ý nghĩa cấu trúc."""
    # Mã cạnh duy nhất trong graph.
    edge_id: str
    # Node nguồn.
    source_node_id: str
    # Node đích.
    target_node_id: str
    # Loại cạnh: input/output/target/entity...
    edge_type: ProblemGraphEdgeType
    # Vị trí input nếu một operation có nhiều input.
    position: Optional[int] = Field(default=None, ge=0)
    # Độ tin cậy của cạnh.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Nguồn tạo cạnh.
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    # Ghi chú phụ.
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
    """Đồ thị có cấu trúc của đề bài sau khi formalize."""
    # Danh sách node của graph.
    nodes: List[ProblemGraphNode] = Field(default_factory=list)
    # Danh sách cạnh của graph.
    edges: List[ProblemGraphEdge] = Field(default_factory=list)
    # Node đích cuối cùng của graph, thường trùng target_variable.
    target_node_id: Optional[str] = Field(default=None)
    # Độ tin cậy tổng quát của graph.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Nguồn sinh graph.
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    # Ghi chú phụ.
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
    """
    Biểu diễn có cấu trúc của đề bài.

    Đây là output chính của problem formalizer:
    - giữ các quantity đã trích
    - giữ target mà bài đang hỏi
    - giữ các relation candidate
    - có thể kèm problem_graph nếu đã build được đồ thị
    """
    # Toàn bộ đề bài gốc.
    problem_text: str
    # Các quantity đã được trích và chuẩn hóa từ đề.
    quantities: List[QuantityAnnotation] = Field(default_factory=list)
    # Các entity được nhận diện trong đề.
    entities: List[ProblemEntity] = Field(default_factory=list)
    # Target spec - bài đang hỏi cái gì.
    target: Optional[TargetSpec] = Field(default=None)
    # Các giả thuyết quan hệ toán học ở mức coarse.
    relation_candidates: List[RelationCandidate] = Field(default_factory=list)
    # Đồ thị cấu trúc của bài toán, nếu đã formalize được.
    problem_graph: Optional[ProblemGraph] = Field(default=None)
    # Các giả định mà hệ thống phải chấp nhận khi formalize.
    assumptions: List[str] = Field(default_factory=list)
    # Độ tin cậy tổng quát của formalization này.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # FormalizedProblem này đến từ heuristic, llm, hay nguồn khác.
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    # Ghi chú debug/repair/fallback.
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
    """Một bước thực thi được trong runtime/executable plan."""
    # Mã bước duy nhất trong plan.
    step_id: str
    # Phép toán chuẩn hóa của bước.
    operation: TraceOperation = Field(default=TraceOperation.UNKNOWN)
    # Biểu thức có thể thực thi hoặc symbolic expression của bước.
    expression: str = Field(description="Executable symbolic expression or normalized formula")
    # Danh sách ref đầu vào mà bước này cần.
    input_refs: List[str] = Field(default_factory=list, description="Quantity ids or variable refs")
    # Ref đầu ra mà bước này tạo ra.
    output_ref: str = Field(description="Variable name produced by this step")
    # Giải thích ngắn cho bước.
    explanation: Optional[str] = Field(default=None)
    # Nếu có, đây là code thực thi cụ thể tương ứng.
    executable_code: Optional[str] = Field(default=None, description="Optional Python snippet or executable code")
    # Độ tin cậy của bước.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Nguồn tạo step.
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
    """Kế hoạch thực thi đầy đủ để solver/executor tính ra đáp án chuẩn."""
    # Mã plan.
    plan_id: str
    # Ref đích cuối cùng plan cần tính ra.
    target_ref: str
    # Các bước thực thi theo thứ tự.
    steps: List[ExecutableStep] = Field(default_factory=list)
    # Giả định cần thiết để plan chạy.
    assumptions: List[str] = Field(default_factory=list)
    # Độ tin cậy của plan.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Nguồn tạo plan.
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)
    # Ghi chú phụ.
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
    """Kết quả chạy thực tế của một ExecutableStep."""
    # Mã step tương ứng.
    step_id: str
    # Phép toán của step đó.
    operation: TraceOperation = Field(default=TraceOperation.UNKNOWN)
    # Các input số đã resolve thực tế lúc chạy.
    resolved_inputs: List[float] = Field(default_factory=list)
    # Giá trị đầu ra nếu step chạy thành công.
    output_value: Optional[float] = Field(default=None)
    # Step có chạy thành công không.
    success: bool = Field(default=True)
    # Nếu fail thì thông báo lỗi ở đây.
    error_message: Optional[str] = Field(default=None)
    # Ghi chú phụ.
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
    """Toàn bộ trace chạy plan trong runtime."""
    # Plan mà trace này thuộc về.
    plan_id: str
    # Kết quả từng step trong plan.
    step_results: List[ExecutionStepResult] = Field(default_factory=list)
    # Giá trị cuối cùng của plan nếu chạy xong.
    final_value: Optional[float] = Field(default=None)
    # Cả plan có chạy thành công không.
    success: bool = Field(default=False)
    # Lỗi tổng quát nếu trace fail.
    error_message: Optional[str] = Field(default=None)
    # Độ tin cậy của trace.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Ghi chú phụ.
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_final_value_on_success(self):
        if self.success and self.final_value is None:
            raise ValueError("Successful execution trace must include final_value")
        return self


class SolverCandidate(BaseModel):
    """Một ứng viên solver/plan mà runtime có thể chọn để dựng reference."""
    # Mã candidate.
    candidate_id: str
    # Executable plan cụ thể của candidate này.
    executable_plan: ExecutablePlan
    # Lý giải/rendering đi kèm nếu có.
    rendered_reasoning: Optional[str] = Field(default=None)
    # Điểm dùng để chọn candidate tốt nhất.
    selection_score: float = Field(default=0.0)
    # Ghi chú về quá trình chọn candidate này.
    selection_notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_candidate_id(self):
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        return self


class CanonicalReference(BaseModel):
    """
    Lời giải chuẩn nội bộ của hệ thống.

    Đây là artifact chuẩn dùng để:
    - so sánh với bài làm học sinh
    - build evidence
    - làm cơ sở cho diagnosis và hint
    """
    # Đáp án cuối cùng của lời giải chuẩn.
    final_answer: float
    # Bản formalized problem dùng để sinh reference này.
    formalized_problem: FormalizedProblem
    # Plan đã được chọn để giải bài.
    chosen_plan: ExecutablePlan
    # Trace chạy thực tế của chosen_plan.
    execution_trace: ExecutionTrace
    # Lời giải render ra text nếu có.
    rendered_solution_text: Optional[str] = Field(default=None)
    # Tên model nguồn nếu reference có thành phần sinh bởi model.
    source_model: Optional[str] = Field(default=None)
    # Độ tin cậy tổng quát.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Ghi chú phụ.
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_reference_consistency(self):
        if self.execution_trace.success and self.execution_trace.final_value is not None:
            if abs(self.execution_trace.final_value - self.final_answer) > 1e-9:
                raise ValueError("CanonicalReference final_answer must match successful execution_trace.final_value")
        return self


class StudentStepAttempt(BaseModel):
    """Một bước bài làm học sinh sau khi được parser/LLM formalize."""
    # Mã bước của học sinh.
    step_id: str
    # Câu hoặc span text gốc của bước.
    raw_text: str
    # Phép toán mà hệ thống suy ra cho bước này.
    operation: Optional[TraceOperation] = Field(default=None)
    # Các giá trị input số đọc được hoặc suy được từ bước này.
    input_values: List[float] = Field(default_factory=list)
    # Giá trị được học sinh tạo ra ở bước này nếu có.
    extracted_value: Optional[float] = Field(default=None)
    # Các ref mà bước này đang nhắc tới hoặc dùng tới.
    referenced_ids: List[str] = Field(default_factory=list)
    # Độ tin cậy của formalization cho bước này.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Ghi chú phụ.
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_step_attempt_id(self):
        if not self.step_id.strip():
            raise ValueError("step_id must not be empty")
        return self


class StudentSemanticFact(BaseModel):
    """Một fact ngữ nghĩa trung gian mà hệ thống suy ra từ bài làm học sinh."""
    # Mã fact.
    fact_id: str
    # Nhãn ngắn mô tả fact này.
    label: str
    # Giá trị số của fact nếu có.
    value: Optional[float] = Field(default=None)
    # Đoạn grounding trong bài làm học sinh nếu có.
    grounding: Optional[str] = Field(default=None)
    # Độ tin cậy của fact.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Ghi chú phụ.
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
    """
    Biểu diễn có cấu trúc của bài làm học sinh.

    Đây là output chính của student formalizer:
    - giữ đáp án cuối đã chuẩn hóa
    - giữ mode hiểu bài làm
    - giữ semantic facts và các step
    - có thể kèm student_graph
    """
    # Toàn bộ câu trả lời gốc của học sinh.
    raw_answer: str
    # Đáp án cuối chuẩn hóa nếu hệ thống đọc được.
    normalized_final_answer: Optional[float] = Field(default=None)
    # Hệ thống hiểu bài ở mức nào: chỉ có đáp án cuối, trace một phần, full trace...
    mode: StudentWorkMode = Field(default=StudentWorkMode.FINAL_ANSWER_ONLY)
    # Các fact trung gian rút ra từ bài học sinh.
    semantic_facts: List[StudentSemanticFact] = Field(default_factory=list)
    # Các bước bài làm học sinh đã được formalize.
    steps: List[StudentStepAttempt] = Field(default_factory=list)
    # Đồ thị biểu diễn cấu trúc bài làm học sinh nếu đã build được.
    student_graph: Optional[ProblemGraph] = Field(default=None)
    # Ref mà hệ thống cho rằng học sinh đang nhắm tới.
    selected_target_ref: Optional[str] = Field(default=None)
    # Giả định dùng khi formalize bài làm.
    assumptions: List[str] = Field(default_factory=list)
    # Độ tin cậy tổng quát.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Ghi chú phụ/debug/repair.
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
    """Một mẩu evidence cụ thể dùng để hỗ trợ diagnosis."""
    # Loại evidence, ví dụ mismatch/final_answer/path/... tùy builder quy ước.
    evidence_type: str
    # Mô tả ngắn evidence này nói gì.
    description: str
    # Độ tin cậy của evidence item.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Step bên reference mà evidence này gắn với.
    reference_step_id: Optional[str] = Field(default=None)
    # Step bên student mà evidence này gắn với.
    student_step_id: Optional[str] = Field(default=None)
    # Các quantity liên quan đến evidence này.
    quantity_ids: List[str] = Field(default_factory=list)
    # Metadata mở rộng cho evidence item.
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_evidence_type(self):
        if not self.evidence_type.strip():
            raise ValueError("evidence_type must not be empty")
        return self


class DiagnosisEvidence(BaseModel):
    """Toàn bộ evidence sau khi so sánh reference với student work."""
    # Danh sách evidence item chi tiết.
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    # Bản đồ alignment giữa step reference và step student.
    alignment_map: List[Dict[str, Any]] = Field(default_factory=list)
    # Step divergence đầu tiên nếu tìm được.
    first_divergence_step_id: Optional[str] = Field(default=None)
    # Các cơ chế lỗi có khả năng cao do builder suy ra.
    likely_error_mechanisms: List[str] = Field(default_factory=list)
    # Độ tin cậy tổng quát của evidence.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Ghi chú phụ.
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class GraphValidationIssue(BaseModel):
    """Một lỗi hoặc cảnh báo phát hiện trong quá trình validate graph."""
    # Mã lỗi ngắn, dùng để phân loại issue.
    code: str
    # Thông báo mô tả issue.
    message: str
    # Node liên quan nếu có.
    node_id: Optional[str] = Field(default=None)
    # Edge liên quan nếu có.
    edge_id: Optional[str] = Field(default=None)
    # Step liên quan nếu có.
    step_id: Optional[str] = Field(default=None)
    # Thông tin chi tiết mở rộng.
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
    """Kết quả validate tổng quát của một graph/problem graph/student graph."""
    # Graph có hợp lệ không.
    is_valid: bool = Field(default=False)
    # Danh sách issue nếu graph không hợp lệ hoặc có cảnh báo.
    issues: List[GraphValidationIssue] = Field(default_factory=list)
    # Target node mà validator nhìn thấy/resolve được.
    target_node_id: Optional[str] = Field(default=None)
    # Số lượng operation node trong graph.
    operation_node_count: int = Field(default=0, ge=0)
    # Ghi chú phụ.
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DiagnosisResult(BaseModel):
    """Kết quả chẩn đoán cuối cùng về lỗi của học sinh."""
    # Nhãn lỗi chính.
    diagnosis_label: DiagnosisLabel
    # Phân loại con nếu hệ thống có.
    subtype: Optional[str] = Field(default=None)
    # Hệ thống cho rằng lỗi nằm ở đâu.
    localization: ErrorLocalization = Field(default=ErrorLocalization.UNKNOWN)
    # Step mục tiêu mà diagnosis trỏ tới nếu có.
    target_step_id: Optional[str] = Field(default=None)
    # Tóm tắt ngắn bằng text của diagnosis.
    summary: str = Field(default="")
    # Các loại evidence chính dùng để chống lưng cho diagnosis này.
    supporting_evidence_types: List[str] = Field(default_factory=list)
    # Độ tin cậy của diagnosis.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Ghi chú phụ.
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_summary(self):
        if not self.summary.strip():
            raise ValueError("summary must not be empty")
        return self


class HintPlan(BaseModel):
    """Kế hoạch sư phạm để sinh hint, chưa phải hint text cuối."""
    # Diagnosis mà hint plan này đang xử lý.
    diagnosis_label: DiagnosisLabel
    # Mức độ hint: conceptual / relational / next_step.
    hint_level: HintLevel
    # Teacher move chính mà hint nên đi theo.
    teacher_move: TeacherMove
    # Step mục tiêu nếu hint đang nhắm tới một bước cụ thể.
    target_step_id: Optional[str] = Field(default=None)
    # Ngân sách tiết lộ - cho phép hint nói rõ đến mức nào.
    disclosure_budget: int = Field(default=1, ge=0, le=5)
    # Các điểm trọng tâm hint nên chạm tới.
    focus_points: List[str] = Field(default_factory=list)
    # Những điều hint không được tiết lộ trực tiếp.
    must_not_reveal: List[str] = Field(default_factory=list)
    # Lý do sư phạm đằng sau plan này.
    rationale: str = Field(default="")
    # Độ tin cậy của hint plan.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_focus_points(self):
        if self.disclosure_budget == 0 and self.focus_points:
            raise ValueError("focus_points should be empty when disclosure_budget is 0")
        return self


class HintResult(BaseModel):
    """Kết quả hint cuối cùng trả cho người học."""
    # Nội dung hint bằng text.
    hint_text: str
    # Mức độ hint thực tế của hint này.
    hint_level: HintLevel
    # Chế độ render hint nếu hệ thống dùng mode đặc biệt.
    hint_mode: HintMode = Field(default=HintMode.NORMAL)
    # Hint này có qua verifier hay không.
    verification_passed: bool = Field(default=False)
    # Nếu verifier fail thì các rule bị vi phạm nằm ở đây.
    violated_rules: List[str] = Field(default_factory=list)
    # Độ tin cậy của hint cuối.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Ghi chú phụ.
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_hint_text(self):
        if not self.hint_text.strip():
            raise ValueError("hint_text must not be empty")
        return self


class TutoringResult(BaseModel):
    """
    Artifact cuối cùng gom toàn bộ kết quả của pipeline tutoring.

    Tức là một object duy nhất chứa:
    - problem formalization
    - canonical reference
    - student work formalization
    - evidence
    - diagnosis
    - hint plan
    - hint result
    """
    # Kết quả formalize đề bài.
    problem: FormalizedProblem
    # Lời giải chuẩn nội bộ của hệ thống.
    reference: CanonicalReference
    # Bài làm học sinh sau khi formalize.
    student_work: StudentWorkState
    # Evidence so sánh reference và student.
    evidence: DiagnosisEvidence
    # Diagnosis cuối cùng.
    diagnosis: DiagnosisResult
    # Kế hoạch sư phạm trước khi sinh hint.
    hint_plan: HintPlan
    # Hint cuối cùng trả ra.
    hint_result: HintResult

    model_config = ConfigDict(extra="forbid")
