"""Schema compatibility and agreement with runtime argument validation."""

import inspect
import json

import pytest
from openai.types.chat import ChatCompletionToolParam
from pydantic import TypeAdapter, ValidationError

from backend.tools.definitions import get_tool_definitions
from backend.tools.models import HistoryRequest, PanelRequest, TrendRequest
from backend.tools.runtime import ScenarioToolRuntime


REQUEST_MODELS = {
    "get_current_snapshot": PanelRequest,
    "get_sensor_history": HistoryRequest,
    "calculate_phase_imbalance": PanelRequest,
    "calculate_temperature_trend": TrendRequest,
    "get_maintenance_context": PanelRequest,
}


def test_openai_compatible_tool_schemas() -> None:
    tools = get_tool_definitions()
    assert len(tools) == 5
    assert TypeAdapter(list[ChatCompletionToolParam]).validate_python(tools) == tools
    assert json.loads(json.dumps(tools, allow_nan=False)) == tools
    assert {tool["function"]["name"] for tool in tools} == set(REQUEST_MODELS)
    for tool in tools:
        assert tool["type"] == "function"
        function = tool["function"]
        assert function["strict"] is True
        assert function["description"]
        schema = function["parameters"]
        assert schema == REQUEST_MODELS[function["name"]].model_json_schema()
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        arguments = set(inspect.signature(getattr(ScenarioToolRuntime, function["name"])).parameters) - {"self"}
        assert arguments == set(schema["properties"])
        assert schema["properties"]["panel_id"]["type"] == "string"


def test_sensor_and_lookback_constraints() -> None:
    tools = {tool["function"]["name"]: tool["function"] for tool in get_tool_definitions()}
    properties = tools["get_sensor_history"]["parameters"]["properties"]
    assert set(properties["sensor"]["enum"]) == {
        "voltage_a", "voltage_b", "voltage_c", "current_a", "current_b", "current_c", "temperature"
    }
    for name in ("get_sensor_history", "calculate_temperature_trend"):
        minutes = tools[name]["parameters"]["properties"]["minutes"]
        assert minutes["type"] == "number"
        assert minutes["exclusiveMinimum"] == 0


@pytest.mark.parametrize("name", list(REQUEST_MODELS))
def test_arguments_accept_only_documented_properties(name: str) -> None:
    model = REQUEST_MODELS[name]
    arguments = {"panel_id": "GP-017"}
    if "minutes" in model.model_fields:
        arguments["minutes"] = 60
    if "sensor" in model.model_fields:
        arguments["sensor"] = "temperature"
    assert model.model_validate_json(json.dumps(arguments)).panel_id == "GP-017"
    with pytest.raises(ValidationError):
        model.model_validate({**arguments, "unexpected": True})


def test_definitions_are_independent_and_contain_no_scenario_annotations() -> None:
    definitions = get_tool_definitions()
    serialized = json.dumps(definitions).lower()
    for forbidden in (
        "hidden_ground_truth", "expected_relevant_evidence", "overload", "overheating",
        "normal_or_insufficient", "case-001", "gp-017", "diagnosis", "dangerous", "faulty",
    ):
        assert forbidden not in serialized
    definitions[0]["function"]["parameters"].clear()
    assert get_tool_definitions()[0]["function"]["parameters"]["type"] == "object"
