"""Verify the authored primary inputs and deterministic evaluation pack."""

from collections import Counter
from datetime import timedelta
from typing import get_args

from backend.evaluation.runner import load_evaluation_cases
from backend.scenarios.loader import load_scenarios
from backend.scenarios.models import GroundTruth, ScenarioData
from backend.tools.electrical import calculate_phase_imbalance, calculate_temperature_trend
from backend.tools.runtime import ScenarioToolRuntime


MEASUREMENTS = ("voltage_a", "voltage_b", "voltage_c", "current_a", "current_b", "current_c", "temperature")


def test_four_primary_cases_load_with_allowed_labels() -> None:
    cases = load_scenarios()
    assert [(case.case_id, case.hidden_ground_truth) for case in cases] == [
        ("CASE-001", "connection_related_overheating"), ("CASE-002", "phase_imbalance"),
        ("CASE-003", "overload"), ("CASE-004", "normal_or_insufficient"),
    ]
    assert [case.panel_id for case in cases] == ["GP-021", "GP-017", "GP-033", "GP-044"]
    assert cases[0].optional_image == "demo/assets/case_001_terminal.jpg"
    assert all(case.optional_image is None for case in cases[1:])


def test_primary_measurements_match_the_specified_inputs() -> None:
    # Explicit user-authored values, independent of scenario serialization.
    expected = {
        "CASE-001": [
            [230.5,230.2,230.7,18.0,18.4,18.1,47.0], [230.4,230.1,230.6,18.1,18.5,18.2,49.8],
            [230.3,230.0,230.5,18.1,18.6,18.2,54.3], [230.5,230.2,230.7,18.2,18.7,18.3,60.0],
            [230.4,230.1,230.6,18.2,18.8,18.4,66.5], [230.4,230.1,230.6,18.3,18.9,18.4,72.1],
            [230.4,230.1,230.6,18.3,19.1,18.5,76.8],
        ],
        "CASE-003": [
            [230.2,230.0,230.3,20.0,20.3,19.8,48.0], [230.1,229.9,230.2,22.1,22.5,21.9,50.1],
            [230.0,229.8,230.1,24.5,24.8,24.1,53.0], [229.9,229.7,230.0,27.0,27.4,26.7,57.0],
            [229.9,229.6,230.0,29.3,29.8,29.0,61.5], [229.8,229.5,229.9,30.7,31.2,30.4,65.0],
            [229.8,229.5,229.9,31.8,32.4,31.5,68.5],
        ],
        "CASE-004": [
            [230.2,230.0,230.3,17.7,18.0,17.8,54.8], [230.1,230.1,230.2,17.8,18.0,17.9,55.1],
            [230.2,230.0,230.2,17.7,18.1,17.8,55.0], [230.1,230.0,230.3,17.8,18.0,17.9,55.2],
            [230.2,230.1,230.2,17.8,18.1,17.9,55.3], [230.1,230.0,230.2,17.8,18.0,17.9,55.4],
            [230.1,230.0,230.2,17.8,18.1,17.9,61.0],
        ],
    }
    for case in load_scenarios():
        if case.case_id not in expected:
            continue
        points = [*case.history, case.initial_snapshot]
        assert [[getattr(point, name) for name in MEASUREMENTS] for point in points] == expected[case.case_id]
        assert all(point.timestamp.date().isoformat() == "2026-11-03" for point in points)
        assert [point.timestamp.strftime("%H:%M") for point in points] == [
            "08:00", "08:10", "08:20", "08:30", "08:40", "08:50", "09:00"
        ]


def test_eight_evaluation_cases_are_distinct_and_balanced() -> None:
    primary = load_scenarios()
    evaluation = load_evaluation_cases()
    assert len(evaluation) == 8
    assert Counter(case.hidden_ground_truth for case in evaluation) == {label: 2 for label in get_args(GroundTruth)}
    all_cases = primary + evaluation
    assert len({case.case_id for case in all_cases}) == 12
    primary_rows = {
        tuple(getattr(point, name) for name in MEASUREMENTS)
        for case in primary for point in [*case.history, case.initial_snapshot]
    }
    signatures = []
    for case in evaluation:
        rows = [tuple(getattr(point, name) for name in MEASUREMENTS) for point in [*case.history, case.initial_snapshot]]
        assert all(row not in primary_rows for row in rows)
        signatures.append(tuple(rows))
        assert len(case.history) == 6
        assert case.initial_snapshot.timestamp - case.history[0].timestamp == timedelta(minutes=60)
    assert len(set(signatures)) == 8
    assert load_evaluation_cases() == evaluation


def test_evaluation_variants_preserve_multi_measurement_patterns() -> None:
    cases = load_evaluation_cases()
    for case in cases:
        if case.hidden_ground_truth == "overload":
            for name in ("current_a", "current_b", "current_c"):
                assert getattr(case.initial_snapshot, name) > getattr(case.history[0], name)
        if case.hidden_ground_truth == "normal_or_insufficient":
            temperatures = [point.temperature for point in case.history]
            assert max(temperatures) - min(temperatures) < case.initial_snapshot.temperature - temperatures[-1]
            assert case.maintenance_context.known_previous_alerts == []
        if case.hidden_ground_truth == "connection_related_overheating":
            assert case.optional_image is None
            assert calculate_temperature_trend(case.history, case.initial_snapshot).temperature_change > 0
    phase_cases = [case for case in cases if case.hidden_ground_truth == "phase_imbalance"]
    assert {
        calculate_phase_imbalance(case.initial_snapshot.current_a, case.initial_snapshot.current_b, case.initial_snapshot.current_c).most_deviant_phase
        for case in phase_cases
    } == {"A", "C"}


def test_every_case_projection_hides_evaluation_annotations() -> None:
    for case in [*load_scenarios(), *load_evaluation_cases()]:
        assert case.hidden_ground_truth in get_args(GroundTruth)
        data = case.to_scenario_data()
        assert type(data) is ScenarioData
        assert "hidden_ground_truth" not in data.model_dump()
        assert "expected_relevant_evidence" not in data.model_dump()
        initial = ScenarioToolRuntime(data, reliability=1.0).initial_context().model_dump()
        assert set(initial) == {"case_id", "panel_id", "initial_snapshot"}
