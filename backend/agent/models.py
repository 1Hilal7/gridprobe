"""Investigation outputs, chronological trace events, and usage accounting."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from backend.agent.contracts import DiagnosisResult
from backend.evidence.models import EvidenceRecord


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentErrorInfo(AgentModel):
    code: str
    message: str


class TraceStep(AgentModel):
    """An ordered event; tool results contain only explicitly requested data."""

    step_number: int = Field(ge=1)
    kind: Literal["MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT", "MAX_STEP_TERMINATION"]
    phase: Literal["INVESTIGATION", "FINALIZATION"] = "INVESTIGATION"
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_arguments: dict[str, JsonValue] | None = None
    tool_result: dict[str, JsonValue] | None = None
    assistant_content: str | None = None
    evidence_ids_added: list[str] = Field(default_factory=list)
    error: AgentErrorInfo | None = None


class ModelUsageSummary(AgentModel):
    """Sum available SDK usage across investigation, finalization, and Muse vision requests.

    Null totals mean unavailable. requests_with_usage indicates whether totals
    cover every request. Reasoning tokens are a subset of output tokens and
    are not added to total_tokens again. No prices or costs are inferred.
    """

    request_count: int = 0
    requests_with_usage: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None


class InvestigationResult(AgentModel):
    case_id: str
    panel_id: str
    trace: list[TraceStep]
    evidence: list[EvidenceRecord]
    diagnosis: DiagnosisResult
    usage: ModelUsageSummary
    termination_reason: Literal["NATURAL_STOP", "MAX_AGENT_STEPS"]
    termination_error: AgentErrorInfo | None = None
