"""Schema/loader tests using structural fixtures, not diagnostic scenarios."""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.scenarios.loader import load_scenario, load_scenarios
from backend.scenarios.models import ScenarioCase, ScenarioData, TelemetryHistoryPoint


@pytest.fixture
def case_data() -> dict[str, Any]:
    sample = {
        "timestamp": "2026-01-01T12:00:00Z",
        "voltage_a": 230.0,
        "voltage_b": 230.0,
        "voltage_c": 230.0,
        "current_a": 10.0,
        "current_b": 10.0,
        "current_c": 10.0,
        "temperature": 25.0,
    }
    return {
        "case_id": "schema-test",
        "panel_id": "test-panel",
        "hidden_ground_truth": "normal_or_insufficient",
        "initial_snapshot": sample.copy(),
        "history": [sample.copy()],
        "maintenance_context": {
            "last_inspection_date": "2025-12-01",
            "known_previous_alerts": [],
            "recent_maintenance_note": None,
        },
        "optional_image": None,
        "expected_relevant_evidence": [],
    }


def test_load_valid_scenario(tmp_path: Path, case_data: dict[str, Any]) -> None:
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case_data), encoding="utf-8")

    case = load_scenario(path)

    assert case.case_id == "schema-test"
    assert case.initial_snapshot.timestamp == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert case.initial_snapshot.current_a == 10.0
    assert isinstance(case.history[0], TelemetryHistoryPoint)
    assert case.maintenance_context.last_inspection_date == date(2025, 12, 1)
    assert case.optional_image is None
    assert case.model_dump(mode="json") == case_data
    assert load_scenario(path) == case


@pytest.mark.parametrize(
    "label",
    ["overload", "phase_imbalance", "connection_related_overheating", "normal_or_insufficient"],
)
def test_allowed_ground_truth(case_data: dict[str, Any], label: str) -> None:
    case_data["hidden_ground_truth"] = label
    assert ScenarioCase.model_validate(case_data).hidden_ground_truth == label


@pytest.mark.parametrize("label", ["normal", "insufficient", "OVERLOAD", "unknown", "", None, 1])
def test_reject_other_ground_truth(case_data: dict[str, Any], label: Any) -> None:
    case_data["hidden_ground_truth"] = label
    with pytest.raises(ValidationError):
        ScenarioCase.model_validate(case_data)


@pytest.mark.parametrize(
    "field",
    ["case_id", "panel_id", "hidden_ground_truth", "initial_snapshot", "history",
     "maintenance_context", "optional_image", "expected_relevant_evidence"],
)
def test_reject_missing_case_fields(
    tmp_path: Path, case_data: dict[str, Any], field: str,
) -> None:
    del case_data[field]
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(case_data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_scenario(path)


@pytest.mark.parametrize("container", ["initial_snapshot", "history"])
@pytest.mark.parametrize(
    "field",
    ["timestamp", "voltage_a", "voltage_b", "voltage_c", "current_a", "current_b", "current_c", "temperature"],
)
def test_reject_incomplete_telemetry(
    case_data: dict[str, Any], container: str, field: str,
) -> None:
    sample = case_data[container][0] if container == "history" else case_data[container]
    del sample[field]
    with pytest.raises(ValidationError):
        ScenarioCase.model_validate(case_data)


@pytest.mark.parametrize("value", ["bad", None, float("nan"), float("inf")])
def test_reject_invalid_measurements(case_data: dict[str, Any], value: Any) -> None:
    case_data["initial_snapshot"]["current_a"] = value
    with pytest.raises(ValidationError):
        ScenarioCase.model_validate(case_data)


@pytest.mark.parametrize(
    "field,value",
    [("history", {}), ("maintenance_context", {}), ("expected_relevant_evidence", "bad"),
     ("optional_image", 42), ("case_id", ""), ("unexpected", True)],
)
def test_reject_invalid_case_data(
    tmp_path: Path, case_data: dict[str, Any], field: str, value: Any,
) -> None:
    case_data[field] = value
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(case_data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_scenario(path)


def test_reject_invalid_timestamp(case_data: dict[str, Any]) -> None:
    case_data["history"][0]["timestamp"] = "not-a-timestamp"
    with pytest.raises(ValidationError):
        ScenarioCase.model_validate(case_data)


def test_reject_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"case_id":', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_scenario(path)


def test_load_directory_in_filename_order(tmp_path: Path, case_data: dict[str, Any]) -> None:
    for filename, case_id in [("b.json", "second"), ("a.json", "first")]:
        (tmp_path / filename).write_text(
            json.dumps({**case_data, "case_id": case_id}), encoding="utf-8"
        )
    (tmp_path / "ignored.txt").write_text("not JSON", encoding="utf-8")
    assert [case.case_id for case in load_scenarios(tmp_path)] == ["first", "second"]


def test_directory_rejects_invalid_case(tmp_path: Path, case_data: dict[str, Any]) -> None:
    (tmp_path / "a.json").write_text(json.dumps(case_data), encoding="utf-8")
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_scenarios(tmp_path)


def test_empty_and_missing_directory(tmp_path: Path) -> None:
    assert load_scenarios(tmp_path) == []
    with pytest.raises(FileNotFoundError):
        load_scenarios(tmp_path / "missing")


def test_evaluation_annotations_are_separate(case_data: dict[str, Any]) -> None:
    case_data["expected_relevant_evidence"] = ["evaluation-only-marker"]
    case = ScenarioCase.model_validate(case_data)
    data = case.to_scenario_data()

    assert type(data) is ScenarioData
    assert data.initial_snapshot == case.initial_snapshot
    assert data.history == case.history
    assert "hidden_ground_truth" not in data.model_dump()
    assert "expected_relevant_evidence" not in data.model_dump()
    assert "normal_or_insufficient" not in data.model_dump_json()
    assert "evaluation-only-marker" not in data.model_dump_json()
    assert not hasattr(data, "hidden_ground_truth")
    with pytest.raises(ValidationError):
        ScenarioData.model_validate(case_data)
