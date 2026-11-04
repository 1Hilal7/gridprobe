"""Evidence validation, ledger isolation, and measurement conversions."""

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from backend.evidence.converters import phase_imbalance_to_evidence, temperature_trend_to_evidence
from backend.evidence.ledger import EvidenceLedger
from backend.evidence.models import EvidenceRecord, EvidenceSource, EvidenceType
from backend.tools.electrical import TemperatureTrendResult, calculate_phase_imbalance


@pytest.fixture
def record_data() -> dict[str, Any]:
    return {
        "id": "EV-001",
        "source": "TELEMETRY",
        "type": "TEMPERATURE_SNAPSHOT",
        "timestamp": "2026-11-03T09:00:00+03:00",
        "summary": "Recorded temperature measurement.",
        "value": 25.5,
        "unit": "celsius",
        "tool_name": None,
        "reliability": 0.8,
        "metadata": {"sensor": {"name": "temperature"}},
    }


def test_valid_evidence(record_data: dict[str, Any]) -> None:
    record = EvidenceRecord.model_validate(record_data)
    assert record.source is EvidenceSource.TELEMETRY
    assert record.type is EvidenceType.TEMPERATURE_SNAPSHOT
    assert isinstance(record.timestamp, datetime)
    assert record.model_dump(mode="json") == record_data


@pytest.mark.parametrize("value", [0, 0.0, -32.1, "observation", True, False, None])
def test_scalar_value_types_preserved(record_data: dict[str, Any], value: Any) -> None:
    record = EvidenceRecord.model_validate({**record_data, "value": value, "unit": None})
    assert record.value == value
    assert type(record.value) is type(value)
    assert record.unit is None


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_reliability_boundaries(record_data: dict[str, Any], value: float) -> None:
    assert EvidenceRecord.model_validate({**record_data, "reliability": value}).reliability == value


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan"), float("inf"), None, True, "0.5"])
def test_invalid_reliability(record_data: dict[str, Any], value: Any) -> None:
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate({**record_data, "reliability": value})


@pytest.mark.parametrize(
    "field,value",
    [("id", ""), ("id", "  "), ("source", "AGENT"), ("type", "DIAGNOSIS"),
     ("timestamp", "invalid"), ("metadata", []), ("metadata", None),
     ("metadata", {"unsupported": object()}), ("value", []), ("value", {}),
     ("value", float("nan")), ("value", float("inf")), ("unexpected", True)],
)
def test_invalid_fields(record_data: dict[str, Any], field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate({**record_data, field: value})


def test_sources_are_exact() -> None:
    assert {source.value for source in EvidenceSource} == {
        "TELEMETRY", "HISTORY", "DETERMINISTIC_ANALYSIS", "MAINTENANCE_CONTEXT", "VISION"
    }


def test_ledger_retrieval_and_duplicate_rejection(record_data: dict[str, Any]) -> None:
    ledger = EvidenceLedger()
    record = EvidenceRecord.model_validate(record_data)
    ledger.add(record)
    assert ledger.get("EV-001") == record
    with pytest.raises(ValueError, match="duplicate evidence ID"):
        ledger.add(EvidenceRecord.model_validate({**record_data, "value": 99}))
    assert ledger.list_all() == [record]
    with pytest.raises(KeyError):
        ledger.get("missing")


def test_ordered_json_export(record_data: dict[str, Any]) -> None:
    ledger = EvidenceLedger()
    for evidence_id in ["EV-002", "EV-001"]:
        ledger.add(EvidenceRecord.model_validate({**record_data, "id": evidence_id}))
    exported = ledger.export()
    assert [record.id for record in ledger.list_all()] == ["EV-002", "EV-001"]
    assert [record["id"] for record in exported] == ["EV-002", "EV-001"]
    assert json.loads(json.dumps(exported, allow_nan=False)) == exported
    assert exported[0]["source"] == "TELEMETRY"
    assert isinstance(exported[0]["timestamp"], str)


def test_empty_ledger() -> None:
    ledger = EvidenceLedger()
    assert ledger.list_all() == []
    assert ledger.export() == []


def test_ledger_protects_stored_records(record_data: dict[str, Any]) -> None:
    ledger = EvidenceLedger()
    record = EvidenceRecord.model_validate(record_data)
    ledger.add(record)
    record.metadata["sensor"]["name"] = "changed original"
    ledger.get("EV-001").metadata["sensor"]["name"] = "changed retrieval"
    ledger.list_all()[0].metadata.clear()
    ledger.export()[0]["metadata"].clear()
    assert ledger.get("EV-001").metadata == {"sensor": {"name": "temperature"}}
    with pytest.raises(ValidationError):
        record.id = "EV-002"


def test_phase_imbalance_conversion() -> None:
    result = calculate_phase_imbalance(15, 60, 15)
    timestamp = datetime(2026, 11, 3, tzinfo=timezone.utc)
    evidence = phase_imbalance_to_evidence(
        result, evidence_id="EV-001", timestamp=timestamp, reliability=0.7
    )
    assert evidence.id == "EV-001"
    assert evidence.timestamp == timestamp
    assert evidence.reliability == 0.7
    assert evidence.source is EvidenceSource.DETERMINISTIC_ANALYSIS
    assert evidence.type is EvidenceType.PHASE_IMBALANCE
    assert evidence.value == result.imbalance_percent
    assert evidence.unit == "percent"
    assert evidence.tool_name == "calculate_phase_imbalance"
    assert evidence.metadata == {"most_deviant_phase": "B", "average_current": 30, "max_deviation": 30}


@pytest.mark.parametrize("change,rate", [(32.1, 0.535), (-18.0, -0.3), (0.0, 0.0)])
def test_temperature_trend_conversion(change: float, rate: float) -> None:
    result = TemperatureTrendResult(
        start_temperature=46.2, end_temperature=46.2 + change,
        temperature_change=change, duration_minutes=60, rate_per_minute=rate,
    )
    timestamp = datetime(2026, 11, 3, tzinfo=timezone.utc)
    evidence = temperature_trend_to_evidence(
        result, evidence_id="EV-002", timestamp=timestamp, reliability=0.6
    )
    assert evidence.timestamp == timestamp
    assert evidence.reliability == 0.6
    assert evidence.source is EvidenceSource.HISTORY
    assert evidence.type is EvidenceType.TEMPERATURE_TREND
    assert evidence.value == change
    assert evidence.unit == "celsius"
    assert evidence.tool_name == "calculate_temperature_trend"
    assert evidence.metadata == {
        "start_temperature": result.start_temperature,
        "end_temperature": result.end_temperature,
        "duration_minutes": 60, "rate_per_minute": rate,
    }
