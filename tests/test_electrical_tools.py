"""Numerical contracts and invalid-input handling for deterministic tools."""

import pytest
from pydantic import ValidationError

from backend.scenarios.models import TelemetryHistoryPoint, TelemetrySnapshot
from backend.tools.electrical import (
    PhaseImbalanceResult,
    TemperatureTrendResult,
    calculate_phase_imbalance,
    calculate_temperature_trend,
)


def measurement(timestamp: str, temperature: float) -> TelemetryHistoryPoint:
    return TelemetryHistoryPoint(
        timestamp=timestamp,
        voltage_a=230, voltage_b=230, voltage_c=230,
        current_a=10, current_b=10, current_c=10,
        temperature=temperature,
    )


def snapshot(timestamp: str, temperature: float) -> TelemetrySnapshot:
    return TelemetrySnapshot.model_validate(measurement(timestamp, temperature).model_dump())


def test_balanced_currents() -> None:
    result = calculate_phase_imbalance(12, 12, 12)
    assert isinstance(result, PhaseImbalanceResult)
    assert result.average_current == 12
    assert result.max_deviation == 0
    assert result.imbalance_percent == 0
    assert result.most_deviant_phase is None


@pytest.mark.parametrize(
    "currents,phase", [((60, 15, 15), "A"), ((15, 60, 15), "B"), ((15, 15, 60), "C")],
)
def test_strongly_imbalanced_currents(currents: tuple[float, float, float], phase: str) -> None:
    result = calculate_phase_imbalance(*currents)
    assert result.average_current == 30
    assert result.max_deviation == 30
    assert result.imbalance_percent == 100
    assert result.most_deviant_phase == phase


def test_fractional_imbalance_and_tie() -> None:
    result = calculate_phase_imbalance(10, 20, 30)
    assert result.average_current == 20
    assert result.max_deviation == 10
    assert result.imbalance_percent == 50
    assert result.most_deviant_phase == "A"
    assert calculate_phase_imbalance(1, 2, 4).imbalance_percent == pytest.approx(500 / 7)


def test_zero_current_average() -> None:
    with pytest.raises(ValueError, match="average_current"):
        calculate_phase_imbalance(0, 0, 0)


@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf"), -float("inf"), True, "10", None])
@pytest.mark.parametrize("phase_index", [0, 1, 2])
def test_invalid_currents(invalid: object, phase_index: int) -> None:
    currents = [10, 10, 10]
    currents[phase_index] = invalid
    with pytest.raises(ValidationError):
        calculate_phase_imbalance(*currents)


def test_overflowing_average() -> None:
    with pytest.raises(ValueError, match="average_current"):
        calculate_phase_imbalance(1e308, 1e308, 1e308)


@pytest.mark.parametrize(
    "start,end,change,rate",
    [(20, 35, 15, 1.5), (35, 20, -15, -1.5), (20, 20, 0, 0),
     (46, 78, 32, 3.2), (78, 60, -18, -1.8)],
)
def test_temperature_trend(start: float, end: float, change: float, rate: float) -> None:
    result = calculate_temperature_trend(
        [measurement("2026-01-01T12:00:00Z", start)],
        snapshot("2026-01-01T12:10:00Z", end),
    )
    assert isinstance(result, TemperatureTrendResult)
    assert result.start_temperature == start
    assert result.end_temperature == end
    assert result.temperature_change == change
    assert result.model_dump()["temperature_change"] == change
    assert result.duration_minutes == 10
    assert result.rate_per_minute == rate


def test_unordered_measurements_and_snapshot() -> None:
    history = [measurement("2026-01-01T12:10:00Z", 40), measurement("2026-01-01T12:00:00Z", 20)]
    original = [point.model_dump() for point in history]
    result = calculate_temperature_trend(history, snapshot("2026-01-01T12:05:00Z", 70))
    assert result.start_temperature == 20
    assert result.end_temperature == 40
    assert result.duration_minutes == 10
    assert result.rate_per_minute == 2
    assert [point.model_dump() for point in history] == original


@pytest.mark.parametrize("history", [[], [measurement("2026-01-01T12:00:00Z", 20)]])
def test_insufficient_or_zero_duration(history: list[TelemetryHistoryPoint]) -> None:
    with pytest.raises(ValueError, match="positive duration"):
        calculate_temperature_trend(history, snapshot("2026-01-01T12:00:00Z", 20))


def test_conflicting_duplicate_timestamps() -> None:
    with pytest.raises(ValueError, match="conflicting temperatures"):
        calculate_temperature_trend(
            [measurement("2026-01-01T12:00:00Z", 20)],
            snapshot("2026-01-01T12:00:00Z", 25),
        )


def test_identical_duplicate_timestamps() -> None:
    point = measurement("2026-01-01T12:00:00Z", 20)
    result = calculate_temperature_trend([point, point], snapshot("2026-01-01T12:00:30Z", 21))
    assert result.duration_minutes == 0.5
    assert result.rate_per_minute == 2


def test_timezone_offsets_are_compared_as_instants() -> None:
    result = calculate_temperature_trend(
        [measurement("2026-01-01T15:00:00+03:00", 20)],
        snapshot("2026-01-01T12:10:00Z", 25),
    )
    assert result.duration_minutes == 10
    assert result.rate_per_minute == 0.5


def test_mixed_timezone_awareness() -> None:
    with pytest.raises(ValueError, match="uniformly timezone-aware or naive"):
        calculate_temperature_trend(
            [measurement("2026-01-01T12:00:00", 20)],
            snapshot("2026-01-01T12:10:00Z", 25),
        )


def test_naive_timestamps_on_same_clock() -> None:
    result = calculate_temperature_trend(
        [measurement("2026-01-01T12:00:00", 20)],
        snapshot("2026-01-01T12:10:00", 25),
    )
    assert result.duration_minutes == 10


def test_invalid_history_timestamp_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        measurement("invalid", 20)


def test_nonfinite_temperature_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        measurement("2026-01-01T12:00:00Z", float("nan"))
