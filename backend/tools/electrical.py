"""Pure electrical measurements; no fault labels or safety thresholds."""

from collections.abc import Sequence
from datetime import datetime, timezone
from math import isfinite
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, validate_call

from backend.scenarios.models import TelemetryHistoryPoint, TelemetrySnapshot


NonNegativeFinite = Annotated[FiniteFloat, Field(ge=0)]


class PhaseImbalanceResult(BaseModel):
    """Current deviations in amperes and imbalance in percent."""

    model_config = ConfigDict(extra="forbid")

    average_current: NonNegativeFinite
    max_deviation: NonNegativeFinite
    imbalance_percent: NonNegativeFinite
    most_deviant_phase: Literal["A", "B", "C"] | None


class TemperatureTrendResult(BaseModel):
    """Endpoint trend in Celsius and minutes; change and rate are signed."""

    model_config = ConfigDict(extra="forbid")

    start_temperature: FiniteFloat
    end_temperature: FiniteFloat
    temperature_change: FiniteFloat
    duration_minutes: Annotated[FiniteFloat, Field(gt=0)]
    rate_per_minute: FiniteFloat


@validate_call(config=ConfigDict(strict=True))
def calculate_phase_imbalance(
    current_a: NonNegativeFinite,
    current_b: NonNegativeFinite,
    current_c: NonNegativeFinite,
) -> PhaseImbalanceResult:
    """Calculate imbalance for finite, nonnegative phase-current magnitudes.

    Zero/nonfinite averages raise ValueError because the ratio is undefined.
    Balanced currents have no most-deviant phase. Other ties prefer A, B, C.
    Invalid inputs raise Pydantic ValidationError (a ValueError subclass).
    """
    currents = (current_a, current_b, current_c)
    average_current = (current_a + current_b + current_c) / 3
    if not isfinite(average_current) or average_current <= 0:
        raise ValueError("average_current must be finite and greater than zero")

    deviations = tuple(abs(current - average_current) for current in currents)
    max_deviation = max(deviations)
    phases: tuple[Literal["A", "B", "C"], ...] = ("A", "B", "C")
    return PhaseImbalanceResult(
        average_current=average_current,
        max_deviation=max_deviation,
        imbalance_percent=(max_deviation / average_current) * 100,
        most_deviant_phase=(
            phases[deviations.index(max_deviation)] if max_deviation > 0 else None
        ),
    )


def calculate_temperature_trend(
    history: Sequence[TelemetryHistoryPoint],
    current_snapshot: TelemetrySnapshot,
) -> TemperatureTrendResult:
    """Sort history plus snapshot and calculate a signed endpoint trend.

    ``temperature_change`` means end minus start in Celsius, not percent change
    or absolute magnitude. Aware timestamps are compared in UTC; uniformly
    naive timestamps use the same assumed clock. Mixed awareness, conflicting
    temperatures at one instant, and zero duration raise ValueError. Identical
    duplicate readings are accepted. The caller's measurements are not changed.
    """
    measurements = [*history, current_snapshot]
    aware = [point.timestamp.utcoffset() is not None for point in measurements]
    if any(aware) and not all(aware):
        raise ValueError("timestamps must be uniformly timezone-aware or naive")

    temperatures: dict[datetime, float] = {}
    for point in measurements:
        timestamp = (
            point.timestamp.astimezone(timezone.utc) if all(aware) else point.timestamp
        )
        if not isfinite(point.temperature):
            raise ValueError("temperatures must be finite")
        if timestamp in temperatures and temperatures[timestamp] != point.temperature:
            raise ValueError("conflicting temperatures at the same timestamp")
        temperatures[timestamp] = point.temperature

    ordered = sorted(temperatures.items())
    start_timestamp, start_temperature = ordered[0]
    end_timestamp, end_temperature = ordered[-1]
    duration_minutes = (end_timestamp - start_timestamp).total_seconds() / 60
    if duration_minutes <= 0:
        raise ValueError("temperature trend requires a positive duration")
    temperature_change = end_temperature - start_temperature
    return TemperatureTrendResult(
        start_temperature=start_temperature,
        end_temperature=end_temperature,
        temperature_change=temperature_change,
        duration_minutes=duration_minutes,
        rate_per_minute=temperature_change / duration_minutes,
    )
