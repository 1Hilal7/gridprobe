"""Input/output contracts for controlled scenario tools."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from backend.scenarios.models import TelemetrySnapshot


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
