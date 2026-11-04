"""Exercise the real CASE-002 fixture through the loader and numerical tools."""

import pytest

from backend.scenarios.models import ScenarioCase
from backend.tools.electrical import (
    calculate_phase_imbalance,
    calculate_temperature_trend,
)


def test_case_002_deterministic_analysis(phase_imbalance_case: ScenarioCase) -> None:
    case = phase_imbalance_case
    assert case.case_id == "CASE-002"
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
