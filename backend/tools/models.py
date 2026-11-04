"""Input/output contracts for controlled scenario tools."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator

from backend.scenarios.models import TelemetrySnapshot
from backend.vision.models import Concept, ConceptRequest
from backend.vision.observation_models import normalize_component


Sensor = Literal[
    "voltage_a", "voltage_b", "voltage_c",
    "current_a", "current_b", "current_c", "temperature",
]
LookbackMinutes = Annotated[FiniteFloat, Field(gt=0, strict=True)]
Reliability = Annotated[FiniteFloat, Field(ge=0, le=1, strict=True)]


class ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PanelRequest(ToolModel):
    panel_id: Annotated[str, Field(min_length=1, strict=True)]


class HistoryRequest(PanelRequest):
    sensor: Sensor
    minutes: LookbackMinutes


class TrendRequest(PanelRequest):
    minutes: LookbackMinutes


class VisualRequest(PanelRequest, ConceptRequest):
    """Panel plus one component noun phrase; never a path or image URL."""


class VisualConditionRequest(PanelRequest):
    component: Concept

    @field_validator("component")
    @classmethod
    def component_name(cls, value: str) -> str:
        return normalize_component(value)


class InitialContext(ToolModel):
    """The complete initial payload allowed outside the runtime."""

    case_id: str
    panel_id: str
    initial_snapshot: TelemetrySnapshot


class SensorHistoryPoint(ToolModel):
    timestamp: datetime
    value: FiniteFloat


class SensorHistoryResult(ToolModel):
    panel_id: str
    sensor: Sensor
    minutes: LookbackMinutes
    points: list[SensorHistoryPoint]
