"""Evidence schemas without diagnostic interpretation."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    JsonValue,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
)


class EvidenceSource(str, Enum):
    TELEMETRY = "TELEMETRY"
    HISTORY = "HISTORY"
    DETERMINISTIC_ANALYSIS = "DETERMINISTIC_ANALYSIS"
    MAINTENANCE_CONTEXT = "MAINTENANCE_CONTEXT"
    VISION = "VISION"


class EvidenceType(str, Enum):
    CURRENT_SNAPSHOT = "CURRENT_SNAPSHOT"
    VOLTAGE_SNAPSHOT = "VOLTAGE_SNAPSHOT"
    TEMPERATURE_SNAPSHOT = "TEMPERATURE_SNAPSHOT"
    PHASE_IMBALANCE = "PHASE_IMBALANCE"
    TEMPERATURE_TREND = "TEMPERATURE_TREND"
    MAINTENANCE_NOTE = "MAINTENANCE_NOTE"
    VISUAL_COMPONENT_OBSERVATION = "VISUAL_COMPONENT_OBSERVATION"


EvidenceValue = StrictInt | StrictFloat | StrictStr | StrictBool | None


class EvidenceRecord(BaseModel):
    """One observation; reliability is supplied by its producer, not inferred."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    source: EvidenceSource
    type: EvidenceType
    timestamp: datetime
    summary: str
    value: EvidenceValue
    unit: str | None
    tool_name: str | None
    reliability: Annotated[FiniteFloat, Field(ge=0, le=1, strict=True)]
    metadata: dict[str, JsonValue]
