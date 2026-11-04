"""Retrieval converters preserve observations without adding interpretation."""

import json
from datetime import date, datetime, timezone

import pytest

from backend.evidence.converters import maintenance_context_to_evidence, sensor_history_to_evidence
from backend.evidence.models import EvidenceSource, EvidenceType
from backend.scenarios.models import MaintenanceContext
from backend.tools.models import Sensor, SensorHistoryPoint, SensorHistoryResult


@pytest.mark.parametrize("sensor,evidence_type,unit", [
    ("current_a", EvidenceType.CURRENT_HISTORY, "amperes"),
    ("current_b", EvidenceType.CURRENT_HISTORY, "amperes"),
    ("current_c", EvidenceType.CURRENT_HISTORY, "amperes"),
    ("voltage_a", EvidenceType.VOLTAGE_HISTORY, "volts"),
    ("voltage_b", EvidenceType.VOLTAGE_HISTORY, "volts"),
    ("voltage_c", EvidenceType.VOLTAGE_HISTORY, "volts"),
    ("temperature", EvidenceType.TEMPERATURE_HISTORY, "celsius"),
])
def test_history_conversion(sensor: Sensor, evidence_type: EvidenceType, unit: str) -> None:
    result = SensorHistoryResult(
        panel_id="test-panel", sensor=sensor, minutes=60,
        points=[
            SensorHistoryPoint(timestamp=datetime(2026, 1, 1, 12, minute, tzinfo=timezone.utc), value=value)
            for minute, value in [(0, 10), (10, 15), (20, 5), (30, 12)]
        ],
    )
    timestamp = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
    record = sensor_history_to_evidence(result, evidence_id="EV-001", timestamp=timestamp, reliability=0.8)
    assert record.id == "EV-001"
    assert record.timestamp == timestamp
    assert record.reliability == 0.8
    assert record.source is EvidenceSource.HISTORY
    assert record.type is evidence_type
    assert record.value is None
    assert record.unit == unit
    assert record.tool_name == "get_sensor_history"
    points = result.model_dump(mode="json")["points"]
    assert record.metadata == {
        "panel_id": "test-panel", "sensor": sensor, "requested_minutes": 60,
        "first_value": 10, "last_value": 12, "minimum_value": 5, "maximum_value": 15,
        "number_of_points": 4, "start_timestamp": points[0]["timestamp"],
        "end_timestamp": points[-1]["timestamp"], "points": points,
    }
    assert record.summary == f"Retrieved 4 timestamped measurements for {sensor}."
    assert json.loads(json.dumps(record.model_dump(mode="json"), allow_nan=False)) == record.model_dump(mode="json")
    result.points.clear()
    assert len(record.metadata["points"]) == 4


def test_empty_history_preserves_absence_of_measurements() -> None:
    result = SensorHistoryResult(panel_id="test-panel", sensor="temperature", minutes=1, points=[])
    record = sensor_history_to_evidence(
        result, evidence_id="EV-001", timestamp=datetime(2026, 1, 1), reliability=1.0,
    )
    assert record.value is None
    assert record.metadata["number_of_points"] == 0
    assert record.metadata["points"] == []
    for field in ("first_value", "last_value", "minimum_value", "maximum_value", "start_timestamp", "end_timestamp"):
        assert record.metadata[field] is None
    assert record.metadata["requested_minutes"] == 1


@pytest.mark.parametrize("known", [True, False])
def test_maintenance_conversion(known: bool) -> None:
    context = MaintenanceContext(
        last_inspection_date=date(2026, 1, 1) if known else None,
        known_previous_alerts=["recorded alert"] if known else [],
        recent_maintenance_note="Recorded inspection note." if known else None,
    )
    timestamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    record = maintenance_context_to_evidence(context, evidence_id="EV-002", timestamp=timestamp, reliability=0.7)
    assert record.id == "EV-002"
    assert record.timestamp == timestamp
    assert record.reliability == 0.7
    assert record.source is EvidenceSource.MAINTENANCE_CONTEXT
    assert record.type is EvidenceType.MAINTENANCE_NOTE
    assert record.tool_name == "get_maintenance_context"
    assert record.unit is None
    assert record.value == context.recent_maintenance_note
    assert record.metadata == context.model_dump(mode="json")
    context.known_previous_alerts.clear()
    assert record.metadata["known_previous_alerts"] == (["recorded alert"] if known else [])


def test_converters_do_not_add_diagnostic_language() -> None:
    timestamp = datetime(2026, 1, 1)
    context = MaintenanceContext(
        last_inspection_date=None, known_previous_alerts=["recorded alert"],
        recent_maintenance_note="Inspection was recorded.",
    )
    history = SensorHistoryResult(
        panel_id="test-panel", sensor="temperature", minutes=60,
        points=[SensorHistoryPoint(timestamp=timestamp, value=25)],
    )
    records = [
        sensor_history_to_evidence(history, evidence_id="EV-001", timestamp=timestamp, reliability=1.0),
        maintenance_context_to_evidence(context, evidence_id="EV-002", timestamp=timestamp, reliability=1.0),
    ]
    serialized = json.dumps([record.model_dump(mode="json") for record in records]).lower()
    for forbidden in ("fault", "diagnosis", "dangerous", "abnormal", "stable", "rising", "overheating", "threshold", "risk_level"):
        assert forbidden not in serialized


def test_existing_note_wording_is_preserved_without_new_interpretation() -> None:
    context = MaintenanceContext(
        last_inspection_date=None, known_previous_alerts=["prior report of overheating"],
        recent_maintenance_note="Prior note described an abnormal reading.",
    )
    record = maintenance_context_to_evidence(
        context, evidence_id="EV-001", timestamp=datetime(2026, 1, 1), reliability=1.0,
    )
    assert record.metadata == context.model_dump(mode="json")
    assert record.value == context.recent_maintenance_note
    assert record.summary == "Retrieved recorded maintenance context."
