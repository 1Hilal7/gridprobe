"""Exercise the real CASE-001 file through the loader and numerical tools."""

from pathlib import Path

import pytest

from backend.scenarios.loader import load_scenario
from backend.tools.electrical import (
    calculate_phase_imbalance,
    calculate_temperature_trend,
)


def test_case_001_deterministic_analysis() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "demo/scenarios/case_001_connection_overheating.json"
    )
    case = load_scenario(path)
    assert case.case_id == "CASE-001"
    data = case.to_scenario_data()
    snapshot = data.initial_snapshot

    imbalance = calculate_phase_imbalance(
        snapshot.current_a, snapshot.current_b, snapshot.current_c
    )
    trend = calculate_temperature_trend(data.history, snapshot)

    assert imbalance.most_deviant_phase == "B"
    assert imbalance.imbalance_percent == pytest.approx(28.1, abs=0.01)
    assert trend.temperature_change == pytest.approx(32.1)
    assert trend.duration_minutes == 60
    assert trend.rate_per_minute == pytest.approx(0.535)
