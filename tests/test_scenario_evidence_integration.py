"""Load CASE-001, run real tools, and preserve their observations as evidence."""

import json
from pathlib import Path

import pytest

from backend.evidence.converters import phase_imbalance_to_evidence, temperature_trend_to_evidence
from backend.evidence.ledger import EvidenceLedger
from backend.evidence.models import EvidenceType
from backend.scenarios.loader import load_scenario
from backend.tools.electrical import calculate_phase_imbalance, calculate_temperature_trend


def test_case_001_evidence_ledger() -> None:
    case = load_scenario(
        Path(__file__).resolve().parents[1]
        / "demo/scenarios/case_001_connection_overheating.json"
    )
    assert case.case_id == "CASE-001"
    data = case.to_scenario_data()
    snapshot = data.initial_snapshot
    phase_result = calculate_phase_imbalance(
        snapshot.current_a, snapshot.current_b, snapshot.current_c
    )
    temperature_result = calculate_temperature_trend(data.history, snapshot)

    ledger = EvidenceLedger()
    # Test-provided reliability values exercise explicit caller attribution.
    ledger.add(phase_imbalance_to_evidence(
        phase_result, evidence_id="EV-001", timestamp=snapshot.timestamp, reliability=0.8
    ))
    ledger.add(temperature_trend_to_evidence(
        temperature_result, evidence_id="EV-002", timestamp=snapshot.timestamp, reliability=0.8
    ))

    phase = ledger.get("EV-001")
    assert phase.type is EvidenceType.PHASE_IMBALANCE
    assert phase.metadata["most_deviant_phase"] == "B"
    assert phase.value == pytest.approx(28.1, abs=0.01)
    trend = ledger.get("EV-002")
    assert trend.type is EvidenceType.TEMPERATURE_TREND
    assert trend.value == pytest.approx(32.1)
    assert trend.metadata["duration_minutes"] == 60
    assert trend.metadata["rate_per_minute"] == pytest.approx(0.535)

    exported = ledger.export()
    assert [record["id"] for record in exported] == ["EV-001", "EV-002"]
    serialized = json.dumps(exported, allow_nan=False).lower()
    for forbidden in (
        "diagnosis", "likely_fault", "hidden_ground_truth", "expected_relevant_evidence",
        "dangerous", "faulty", "overheating", "overload", "risk_level", "threshold",
    ):
        assert forbidden not in serialized
