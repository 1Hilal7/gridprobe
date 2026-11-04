"""Explicit public contracts; evaluation cases and private model text stay internal."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from backend.agent.contracts import DiagnosisResult
from backend.agent.models import ModelUsageSummary
from backend.evidence.models import EvidenceRecord
from backend.scenarios.models import TelemetryHistoryPoint, TelemetrySnapshot


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioSummary(PublicModel):
    case_id: str
    panel_id: str
    initial_snapshot: TelemetrySnapshot
    image_available: bool


class InvestigationCase(ScenarioSummary):
    history: list[TelemetryHistoryPoint]


class InvestigationRequest(PublicModel):
    case_id: Annotated[str, Field(min_length=1, strict=True)]


class PublicTraceStep(PublicModel):
    step_number: int
    kind: Literal["MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT", "MAX_STEP_TERMINATION"]
    phase: Literal["INVESTIGATION", "FINALIZATION"]
    summary: str
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_arguments: dict[str, JsonValue] | None = None
    tool_result: dict[str, JsonValue] | None = None
    evidence_ids_added: list[str] = Field(default_factory=list)


class InvestigationResponse(PublicModel):
    case: InvestigationCase
    trace: list[PublicTraceStep]
    evidence: list[EvidenceRecord]
    diagnosis: DiagnosisResult
    usage: ModelUsageSummary
    estimated_cost_usd: float | None
    cost_is_partial: bool
    model: str
    termination_reason: Literal["NATURAL_STOP", "MAX_AGENT_STEPS"]
