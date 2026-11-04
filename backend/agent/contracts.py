from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DiagnosisStatus = Literal[
    "DIAGNOSIS_READY",
    "NEEDS_MORE_EVIDENCE",
    "NO_ACTIONABLE_DIAGNOSIS",
]

FaultType = Literal[
    "overload",
    "phase_imbalance",
    "connection_related_overheating",
    "unknown",
]

RiskLevel = Literal[
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
    "UNKNOWN",
]


class DiagnosisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DiagnosisStatus
    likely_fault: FaultType
    risk_level: RiskLevel

    confidence: float = Field(ge=0.0, le=1.0)

    evidence_ids: list[str]

    reasoning_summary: str
    recommended_inspection: str

    missing_evidence: list[str]