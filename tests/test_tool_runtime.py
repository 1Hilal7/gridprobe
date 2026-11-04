"""Controlled retrieval and deterministic analysis using the real CASE-001 file."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any, get_args
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.evidence.models import EvidenceSource, EvidenceType
from backend.scenarios.loader import load_scenario
from backend.scenarios.models import ScenarioCase, ScenarioData, TelemetryHistoryPoint
from backend.tools import electrical
from backend.tools.models import Sensor
from backend.tools.runtime import ScenarioToolRuntime


@pytest.fixture
def case() -> ScenarioCase:
    return load_scenario(
        Path(__file__).resolve().parents[1]
        / "demo/scenarios/case_001_connection_overheating.json"
    )


@pytest.fixture
def data(case: ScenarioCase) -> ScenarioData:
    return case.to_scenario_data()


@pytest.fixture
def runtime(data: ScenarioData) -> ScenarioToolRuntime:
    return ScenarioToolRuntime(data, reliability=0.8)


def test_initial_context_contains_only_identifiers_and_snapshot(
    runtime: ScenarioToolRuntime, data: ScenarioData,
) -> None:
    context = runtime.initial_context()
    assert set(context.model_dump()) == {"case_id", "panel_id", "initial_snapshot"}
    assert context.case_id == "CASE-001"
    assert context.panel_id == "GP-017"
    assert context.initial_snapshot == data.initial_snapshot
    context.initial_snapshot.temperature = 0
    assert runtime.initial_context().initial_snapshot.temperature == 78.3


def test_reject_full_case_and_other_input_types(case: ScenarioCase) -> None:
    for invalid in (case, case.model_dump(), None):
        with pytest.raises(TypeError, match="plain ScenarioData"):
            ScenarioToolRuntime(invalid, reliability=0.8)


def test_runtime_retains_independent_data_copy(data: ScenarioData) -> None:
    runtime = ScenarioToolRuntime(data, reliability=0.8)
    data.initial_snapshot.temperature = 0
    data.history.clear()
    data.maintenance_context.known_previous_alerts.clear()
    assert runtime.get_current_snapshot("GP-017").temperature == 78.3
    assert len(runtime.get_sensor_history("GP-017", "temperature", 60).points) == 6
    assert runtime.get_maintenance_context("GP-017").known_previous_alerts


def test_current_snapshot(runtime: ScenarioToolRuntime, data: ScenarioData) -> None:
    snapshot = runtime.get_current_snapshot("GP-017")
    assert snapshot == data.initial_snapshot
    snapshot.current_b = 0
    assert runtime.get_current_snapshot("GP-017").current_b == 27.2
    assert runtime.evidence_ledger.export() == []


@pytest.mark.parametrize("sensor", get_args(Sensor))
def test_history_returns_only_requested_sensor(
    runtime: ScenarioToolRuntime, data: ScenarioData, sensor: Sensor,
) -> None:
    result = runtime.get_sensor_history("GP-017", sensor, 30)
    assert result.sensor == sensor
    assert result.panel_id == "GP-017"
    assert result.minutes == 30
    expected = data.history[3:]
    assert [point.timestamp for point in result.points] == [point.timestamp for point in expected]
    assert [point.value for point in result.points] == [getattr(point, sensor) for point in expected]
    assert all(set(point.model_dump()) == {"timestamp", "value"} for point in result.points)
    record = runtime.evidence_ledger.get("EV-001")
    assert record.metadata["sensor"] == sensor
    assert record.metadata["points"] == result.model_dump(mode="json")["points"]
    assert len(runtime.evidence_ledger.list_all()) == 1


def test_history_sorting_inclusive_boundaries_and_future_exclusion(data: ScenarioData) -> None:
    current = data.initial_snapshot
    current_point = TelemetryHistoryPoint.model_validate(current.model_dump())
    future = current_point.model_copy(update={"timestamp": current.timestamp + timedelta(minutes=1)})
    data.history = [future, current_point, *reversed(data.history)]
    runtime = ScenarioToolRuntime(data, reliability=0.8)
    result = runtime.get_sensor_history("GP-017", "temperature", 30)
    assert [point.timestamp.minute for point in result.points] == [30, 40, 50, 0]
    assert result.points[0].timestamp == current.timestamp - timedelta(minutes=30)
    assert result.points[-1].timestamp == current.timestamp


def test_fractional_and_empty_windows(runtime: ScenarioToolRuntime) -> None:
    assert runtime.get_sensor_history("GP-017", "temperature", 9.5).points == []
    points = runtime.get_sensor_history("GP-017", "temperature", 10).points
    assert len(points) == 1
    assert points[0].value == 73.4


@pytest.mark.parametrize("sensor", ["humidity", "hidden_ground_truth", "expected_relevant_evidence", "__dict__"])
def test_unsupported_sensor_rejection(runtime: ScenarioToolRuntime, sensor: str) -> None:
    with pytest.raises(ValidationError):
        runtime.get_sensor_history("GP-017", sensor, 60)


@pytest.mark.parametrize("minutes", [0, -1, float("nan"), float("inf"), True, "60", None])
def test_invalid_windows(runtime: ScenarioToolRuntime, minutes: Any) -> None:
    with pytest.raises(ValidationError):
        runtime.get_sensor_history("GP-017", "temperature", minutes)
    with pytest.raises(ValidationError):
        runtime.calculate_temperature_trend("GP-017", minutes)
    assert runtime.evidence_ledger.export() == []


@pytest.mark.parametrize(
    "operation,arguments",
    [("get_current_snapshot", {}), ("get_sensor_history", {"sensor": "current_b", "minutes": 60}),
     ("calculate_phase_imbalance", {}), ("calculate_temperature_trend", {"minutes": 60}),
     ("get_maintenance_context", {})],
)
def test_wrong_panel(runtime: ScenarioToolRuntime, operation: str, arguments: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="panel_id does not match"):
        getattr(runtime, operation)("OTHER-PANEL", **arguments)
    assert runtime.evidence_ledger.export() == []


def test_maintenance_context(runtime: ScenarioToolRuntime, data: ScenarioData) -> None:
    context = runtime.get_maintenance_context("GP-017")
    assert context == data.maintenance_context
    assert set(context.model_dump()) == {
        "last_inspection_date", "known_previous_alerts", "recent_maintenance_note"
    }
    context.known_previous_alerts.clear()
    assert runtime.get_maintenance_context("GP-017").known_previous_alerts
    record = runtime.evidence_ledger.get("EV-001")
    assert record.source is EvidenceSource.MAINTENANCE_CONTEXT
    assert record.type is EvidenceType.MAINTENANCE_NOTE
    assert record.metadata == {**data.maintenance_context.model_dump(mode="json"), "panel_id": "GP-017"}
    assert record.value == data.maintenance_context.recent_maintenance_note
    assert len(runtime.evidence_ledger.list_all()) == 1


def test_phase_delegation_and_evidence(runtime: ScenarioToolRuntime) -> None:
    with patch.object(electrical, "calculate_phase_imbalance", wraps=electrical.calculate_phase_imbalance) as calculate:
        result = runtime.calculate_phase_imbalance("GP-017")
    calculate.assert_called_once_with(18.4, 27.2, 18.1)
    record = runtime.evidence_ledger.get("EV-001")
    assert record.type is EvidenceType.PHASE_IMBALANCE
    assert record.value == result.imbalance_percent
    assert record.metadata["most_deviant_phase"] == "B"
    assert record.metadata["panel_id"] == "GP-017"
    assert record.timestamp == runtime.get_current_snapshot("GP-017").timestamp
    assert record.reliability == 0.8


def test_temperature_delegation_uses_window_and_snapshot(
    runtime: ScenarioToolRuntime, data: ScenarioData,
) -> None:
    with patch.object(electrical, "calculate_temperature_trend", wraps=electrical.calculate_temperature_trend) as calculate:
        result = runtime.calculate_temperature_trend("GP-017", 30)
    calculate.assert_called_once_with(data.history[3:], data.initial_snapshot)
    assert result.temperature_change == pytest.approx(18.2)
    assert result.duration_minutes == 30
    record = runtime.evidence_ledger.get("EV-001")
    assert record.type is EvidenceType.TEMPERATURE_TREND
    assert record.value == pytest.approx(18.2)
    assert record.metadata["requested_minutes"] == 30
    assert record.metadata["duration_minutes"] == 30


def test_request_deduplication_and_distinct_windows(runtime: ScenarioToolRuntime) -> None:
    with patch.object(electrical, "calculate_phase_imbalance", wraps=electrical.calculate_phase_imbalance) as phase:
        first = runtime.calculate_phase_imbalance("GP-017")
        assert runtime.calculate_phase_imbalance("GP-017") == first
        first.imbalance_percent = 999
        assert runtime.calculate_phase_imbalance("GP-017").imbalance_percent == pytest.approx(28.1, abs=0.01)
        assert phase.call_count == 1
    with patch.object(electrical, "calculate_temperature_trend", wraps=electrical.calculate_temperature_trend) as trend:
        first_trend = runtime.calculate_temperature_trend("GP-017", 60)
        assert runtime.calculate_temperature_trend("GP-017", 60.0) == first_trend
        first_trend.temperature_change = 999
        assert runtime.calculate_temperature_trend("GP-017", 60).temperature_change == pytest.approx(32.1)
        runtime.calculate_temperature_trend("GP-017", 30)
        runtime.calculate_temperature_trend("GP-017", 61)
        assert trend.call_count == 3
    records = runtime.evidence_ledger.list_all()
    assert [record.id for record in records] == ["EV-001", "EV-002", "EV-003", "EV-004"]
    assert records[1].value == records[3].value
    assert records[1].metadata["requested_minutes"] != records[3].metadata["requested_minutes"]


def test_failed_request_does_not_consume_id(runtime: ScenarioToolRuntime) -> None:
    with pytest.raises(ValueError, match="positive duration"):
        runtime.calculate_temperature_trend("GP-017", 1)
    assert runtime.evidence_ledger.export() == []
    runtime.calculate_phase_imbalance("GP-017")
    assert [record.id for record in runtime.evidence_ledger.list_all()] == ["EV-001"]


def test_investigations_have_independent_sequences(data: ScenarioData) -> None:
    for _ in range(2):
        runtime = ScenarioToolRuntime(data, reliability=0.8)
        runtime.calculate_temperature_trend("GP-017", 60)
        runtime.calculate_phase_imbalance("GP-017")
        assert [record.id for record in runtime.evidence_ledger.list_all()] == ["EV-001", "EV-002"]


def test_mixed_timezone_awareness_rejected(data: ScenarioData) -> None:
    data.history[0].timestamp = data.history[0].timestamp.replace(tzinfo=None)
    with pytest.raises(ValueError, match="uniformly timezone-aware or naive"):
        ScenarioToolRuntime(data, reliability=0.8)


@pytest.mark.parametrize("reliability", [-1, 2, float("nan"), True])
def test_invalid_reliability(data: ScenarioData, reliability: Any) -> None:
    with pytest.raises(ValidationError):
        ScenarioToolRuntime(data, reliability=reliability)


def test_case_001_end_to_end_without_evaluation_annotations(runtime: ScenarioToolRuntime) -> None:
    context = runtime.initial_context()
    panel_id = context.panel_id
    snapshot = runtime.get_current_snapshot(panel_id)
    phase = runtime.calculate_phase_imbalance(panel_id)
    trend = runtime.calculate_temperature_trend(panel_id, 60)
    history = runtime.get_sensor_history(panel_id, "current_b", 60)
    voltage = runtime.get_sensor_history(panel_id, "voltage_b", 60)
    maintenance = runtime.get_maintenance_context(panel_id)
    assert phase.imbalance_percent == pytest.approx(28.1, abs=0.01)
    assert phase.most_deviant_phase == "B"
    assert trend.temperature_change == pytest.approx(32.1)
    assert trend.duration_minutes == 60
    assert trend.rate_per_minute == pytest.approx(0.535)
    records = runtime.evidence_ledger.list_all()
    assert [record.type for record in records] == [
        EvidenceType.PHASE_IMBALANCE, EvidenceType.TEMPERATURE_TREND, EvidenceType.CURRENT_HISTORY,
        EvidenceType.VOLTAGE_HISTORY, EvidenceType.MAINTENANCE_NOTE,
    ]
    assert [record.id for record in records] == [f"EV-{number:03d}" for number in range(1, 6)]
    assert records[0].value == phase.imbalance_percent
    assert records[1].value == trend.temperature_change

    outputs = [context, snapshot, history, voltage, maintenance, phase, trend]
    serialized = json.dumps([
        *[output.model_dump(mode="json") for output in outputs],
        runtime.evidence_ledger.export(),
    ], allow_nan=False)
    for forbidden in ("hidden_ground_truth", "expected_relevant_evidence", "connection_related_overheating", "likely_fault"):
        assert forbidden not in serialized
    assert not hasattr(runtime, "scenario_data")


def test_history_deduplication_uses_sensor_and_normalized_window(runtime: ScenarioToolRuntime) -> None:
    first = runtime.get_sensor_history("GP-017", "current_b", 60)
    original_record = runtime.evidence_ledger.get("EV-001")
    assert runtime.get_sensor_history("GP-017", "current_b", 60.0) == first
    first.points.clear()
    assert len(runtime.get_sensor_history("GP-017", "current_b", 60).points) == 6
    assert runtime.evidence_ledger.list_all() == [original_record]
    runtime.get_sensor_history("GP-017", "current_b", 30)
    runtime.get_sensor_history("GP-017", "voltage_b", 60)
    runtime.get_sensor_history("GP-017", "current_b", 61)
    records = runtime.evidence_ledger.list_all()
    assert [record.id for record in records] == ["EV-001", "EV-002", "EV-003", "EV-004"]
    assert [record.metadata["requested_minutes"] for record in records] == [60, 30, 60, 61]
    assert records[0].metadata["points"] == records[3].metadata["points"]
    assert records[0].metadata["points"] != records[1].metadata["points"]


def test_maintenance_deduplication_and_shared_id_sequence(runtime: ScenarioToolRuntime) -> None:
    first = runtime.get_maintenance_context("GP-017")
    original = runtime.evidence_ledger.get("EV-001")
    first.known_previous_alerts.clear()
    assert runtime.get_maintenance_context("GP-017").known_previous_alerts
    assert runtime.evidence_ledger.list_all() == [original]
    runtime.calculate_phase_imbalance("GP-017")
    runtime.get_sensor_history("GP-017", "temperature", 60)
    runtime.calculate_temperature_trend("GP-017", 60)
    runtime.get_maintenance_context("GP-017")
    assert [record.id for record in runtime.evidence_ledger.list_all()] == ["EV-001", "EV-002", "EV-003", "EV-004"]
    assert runtime.evidence_ledger.get("EV-003").type is EvidenceType.TEMPERATURE_HISTORY


def test_empty_history_retrieval_creates_deduplicated_evidence(runtime: ScenarioToolRuntime) -> None:
    for minutes in (1, 1.0):
        assert runtime.get_sensor_history("GP-017", "temperature", minutes).points == []
    records = runtime.evidence_ledger.list_all()
    assert len(records) == 1
    assert records[0].metadata["number_of_points"] == 0
    assert records[0].metadata["first_value"] is None
    assert records[0].metadata["start_timestamp"] is None
