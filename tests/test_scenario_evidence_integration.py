"""Load CASE-001, run real tools, and preserve their observations as evidence."""

import json
from pathlib import Path

import pytest

from backend.evidence.ledger import EvidenceLedger
from backend.evidence.models import EvidenceType
from backend.scenarios.loader import load_scenario
from backend.tools.runtime import ScenarioToolRuntime


def test_case_001_evidence_ledger() -> None:
    case = load_scenario(
        Path(__file__).resolve().parents[1]
        / "demo/scenarios/case_001_connection_overheating.json"
    )
    assert case.case_id == "CASE-001"
    data = case.to_scenario_data()
    ledger = EvidenceLedger()
    # Test-provided reliability values exercise explicit caller attribution.
    runtime = ScenarioToolRuntime(data, reliability=0.8, evidence_ledger=ledger)
    runtime.calculate_phase_imbalance(data.panel_id)
    runtime.calculate_temperature_trend(data.panel_id, 60)
    current_history = runtime.get_sensor_history(data.panel_id, "current_b", 60)
    voltage_history = runtime.get_sensor_history(data.panel_id, "voltage_b", 60)
    maintenance = runtime.get_maintenance_context(data.panel_id)

    phase = ledger.get("EV-001")
    assert phase.type is EvidenceType.PHASE_IMBALANCE
    assert phase.metadata["most_deviant_phase"] == "B"
    assert phase.value == pytest.approx(28.1, abs=0.01)
    trend = ledger.get("EV-002")
    assert trend.type is EvidenceType.TEMPERATURE_TREND
    assert trend.value == pytest.approx(32.1)
    assert trend.metadata["duration_minutes"] == 60
    assert trend.metadata["rate_per_minute"] == pytest.approx(0.535)

    current = ledger.get("EV-003")
    assert current.type is EvidenceType.CURRENT_HISTORY
    assert current.metadata["points"] == current_history.model_dump(mode="json")["points"]
    assert current.metadata["first_value"] == 18.5
    assert current.metadata["last_value"] == 26.4
    assert current.metadata["number_of_points"] == 6
    voltage = ledger.get("EV-004")
    assert voltage.type is EvidenceType.VOLTAGE_HISTORY
    assert voltage.metadata["points"] == voltage_history.model_dump(mode="json")["points"]
    note = ledger.get("EV-005")
    assert note.type is EvidenceType.MAINTENANCE_NOTE
    assert note.metadata == {**maintenance.model_dump(mode="json"), "panel_id": data.panel_id}

    # Repeating any request adds no evidence and consumes no additional ID.
    runtime.calculate_phase_imbalance(data.panel_id)
    runtime.calculate_temperature_trend(data.panel_id, 60.0)
    runtime.get_sensor_history(data.panel_id, "current_b", 60.0)
    runtime.get_sensor_history(data.panel_id, "voltage_b", 60.0)
    runtime.get_maintenance_context(data.panel_id)

    exported = ledger.export()
    assert [record["id"] for record in exported] == [f"EV-{number:03d}" for number in range(1, 6)]
    serialized = json.dumps(exported, allow_nan=False).lower()
    for forbidden in (
        "diagnosis", "likely_fault", "hidden_ground_truth", "expected_relevant_evidence",
        "dangerous", "faulty", "overheating", "overload", "risk_level", "threshold",
    ):
        assert forbidden not in serialized
