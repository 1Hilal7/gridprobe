"""Scenario schemas; full cases include evaluation-only annotations."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat


GroundTruth = Literal[
    "overload",
    "phase_imbalance",
    "connection_related_overheating",
    "normal_or_insufficient",
]
NonEmptyString = Annotated[str, Field(min_length=1)]


class ScenarioModel(BaseModel):
    """Reject unexpected fields rather than silently losing scenario data."""

    model_config = ConfigDict(extra="forbid")


class TelemetrySnapshot(ScenarioModel):
    """Timestamped measurements, without fault interpretation or thresholds."""

    timestamp: datetime
    voltage_a: FiniteFloat
    voltage_b: FiniteFloat
    voltage_c: FiniteFloat
    current_a: FiniteFloat
    current_b: FiniteFloat
    current_c: FiniteFloat
    temperature: FiniteFloat


class TelemetryHistoryPoint(TelemetrySnapshot):
    """One complete timestamped measurement sample in scenario history."""


class MaintenanceContext(ScenarioModel):
    """Recorded maintenance context; null dates and notes mean unknown."""

    last_inspection_date: date | None
    known_previous_alerts: list[str]
    recent_maintenance_note: str | None


class ScenarioData(ScenarioModel):
    """Scenario inputs without evaluation labels or expected evidence."""

    case_id: NonEmptyString
    panel_id: NonEmptyString
    initial_snapshot: TelemetrySnapshot
    history: list[TelemetryHistoryPoint]
    maintenance_context: MaintenanceContext
    optional_image: NonEmptyString | None


class ScenarioCase(ScenarioData):
    """Internal case for loading/evaluation. Never pass this model to an agent.

    Both annotations below are evaluation-only. Use ``to_scenario_data`` to
    obtain inputs without leaking labels or expected evidence.
    """

    hidden_ground_truth: GroundTruth = Field(repr=False)
    expected_relevant_evidence: list[str] = Field(repr=False)

    def to_scenario_data(self) -> ScenarioData:
        """Project onto a separate schema containing only scenario inputs."""
        return ScenarioData.model_validate(
            self.model_dump(include=set(ScenarioData.model_fields))
        )
