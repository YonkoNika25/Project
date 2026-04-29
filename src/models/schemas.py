from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OperationType(str, Enum):
    """Coarse operation hypothesis used across the new architecture."""
    ADDITIVE = "additive"
    SUBTRACTIVE = "subtractive"
    UNKNOWN = "unknown"


class ProvenanceSource(str, Enum):
    """Origin of a structured artifact or derived evidence."""
    PROBLEM_TEXT = "problem_text"
    SOLVER_REFERENCE = "solver_reference"
    HEURISTIC = "heuristic"
    LLM = "llm"
    EXECUTOR = "executor"
    UNKNOWN = "unknown"


class RelationType(str, Enum):
    """Coarse ontology for mathematical relations."""
    ADDITIVE_COMPOSITION = "additive_composition"
    SUBTRACTIVE_COMPARISON = "subtractive_comparison"
    MULTIPLICATIVE_SCALING = "multiplicative_scaling"
    PARTITION_GROUPING = "partition_grouping"
    RATE_UNIT_RELATION = "rate_unit_relation"
    UNKNOWN = "unknown"


class TraceOperation(str, Enum):
    """Operation types used inside structured traces and executable plans."""
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    PERCENT_OF = "percent_of"
    DERIVE = "derive"
    UNKNOWN = "unknown"


class TraceStep(BaseModel):
    """One structured reasoning or execution step."""
    step_index: int = Field(ge=1)
    raw_text: str
    operation: TraceOperation = Field(default=TraceOperation.UNKNOWN)
    input_values: List[float] = Field(default_factory=list)
    output_value: Optional[float] = Field(default=None)
    output_label: Optional[str] = Field(default=None)
    is_final_target: bool = Field(default=False)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)

    model_config = ConfigDict(extra="forbid")


class SymbolicTrace(BaseModel):
    """Structured multi-step trace extracted from text or execution."""
    steps: List[TraceStep] = Field(default_factory=list)
    final_value: Optional[float] = Field(default=None)
    target_label: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)
    provenance: ProvenanceSource = Field(default=ProvenanceSource.UNKNOWN)

    model_config = ConfigDict(extra="forbid")


class DiagnosisLabel(str, Enum):
    """Base diagnosis taxonomy retained for the new tutoring architecture."""
    CORRECT_ANSWER = "correct_answer"
    ARITHMETIC_ERROR = "arithmetic_error"
    QUANTITY_RELATION_ERROR = "quantity_relation_error"
    TARGET_MISUNDERSTANDING = "target_misunderstanding"
    UNPARSEABLE_ANSWER = "unparseable_answer"
    UNKNOWN_ERROR = "unknown_error"


class ErrorLocalization(str, Enum):
    """Where the student's reasoning likely diverged."""
    NONE = "none"
    FINAL_COMPUTATION = "final_computation"
    INTERMEDIATE_STEP = "intermediate_step"
    COMBINING_QUANTITIES = "combining_quantities"
    TARGET_SELECTION = "target_selection"
    UNKNOWN = "unknown"


class AnswerStatus(str, Enum):
    """Whether the student's final answer is correct, incorrect, or unusable."""
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNPARSEABLE = "unparseable"


class TargetStatus(str, Enum):
    """Whether the student is aiming at the intended target quantity."""
    CORRECT = "correct"
    WRONG = "wrong"
    UNKNOWN = "unknown"


class ReasoningStatus(str, Enum):
    """Status of a specific reasoning dimension inside diagnosis."""
    VALID = "valid"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ProcessStatus(str, Enum):
    """How the student's process relates to the canonical reference."""
    CANONICAL = "canonical"
    EQUIVALENT_NONCANONICAL = "equivalent_noncanonical"
    PARTIAL = "partial"
    NOISY_BUT_VALID = "noisy_but_valid"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"


class AnswerAcceptability(str, Enum):
    """Whether the student's current answer is acceptable for tutoring purposes."""
    ACCEPTABLE = "acceptable"
    UNACCEPTABLE = "unacceptable"
    UNPARSEABLE = "unparseable"


class TargetAlignment(str, Enum):
    """Whether the student is aligned with the requested target quantity."""
    ALIGNED = "aligned"
    MISALIGNED = "misaligned"
    UNKNOWN = "unknown"


class ProcessEquivalence(str, Enum):
    """How the student's process compares to the canonical reference without implying error by default."""
    CANONICAL = "canonical"
    EQUIVALENT_NONCANONICAL = "equivalent_noncanonical"
    PARTIAL_OR_NOISY_BUT_ACCEPTABLE = "partial_or_noisy_but_acceptable"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"


class HintLevel(str, Enum):
    """Pedagogical hint granularity."""
    CONCEPTUAL = "conceptual"
    RELATIONAL = "relational"
    NEXT_STEP = "next_step"


class HintMode(str, Enum):
    """Optional rendering mode for future hint generation."""
    NORMAL = "normal"
    SCAFFOLDING = "scaffolding"
    PEDAGOGY_FOLLOWING = "pedagogy_following"
