"""Evaluation-only report schemas; never send these models to the agent."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.agent.models import InvestigationResult, ModelUsageSummary
from backend.evaluation.config import PricingConfig
from backend.scenarios.models import GroundTruth


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EvaluationError(ReportModel):
    code: str
    message: str


class CaseEvaluation(ReportModel):
    case_id: str
    panel_id: str
    hidden_ground_truth: GroundTruth
    investigation: InvestigationResult | None = None
    error: EvaluationError | None = None
    exact_diagnosis_correct: bool | None
    abstention_correct: bool | None
    unnecessary_diagnosis: bool | None
    valid_evidence_references: int = 0
    total_evidence_references: int = 0
    tool_call_count: int | None = None
    attempt_count: int = Field(default=1, ge=1, le=2)
    attempt_errors: list[EvaluationError] = Field(default_factory=list)


class EvaluationMetrics(ReportModel):
    case_count: int
    completed_case_count: int
    failed_case_count: int
    fault_case_count: int
    normal_or_insufficient_case_count: int
    diagnosis_accuracy: float | None
    correct_abstention_rate: float | None
    unsafe_or_unnecessary_diagnosis_rate: float | None
    evidence_reference_validity: float | None
    valid_evidence_references: int
    total_evidence_references: int
    average_tool_calls: float | None
    average_request_count: float | None
    usage: ModelUsageSummary
    usage_complete: bool
    estimated_api_cost: float | None
    cost_is_partial: bool | None


class EvaluationReport(ReportModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model: str | None = None
    pricing: PricingConfig
    metrics: EvaluationMetrics
    cases: list[CaseEvaluation]
