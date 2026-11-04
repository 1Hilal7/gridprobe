"""Scripted model responses exercise real scenario tools, never the Meta API."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from openai.types.chat import ChatCompletion, ParsedChatCompletion

from backend.agent.contracts import DiagnosisResult
from backend.agent.errors import (
    AgentProviderError, DiagnosisSchemaError, MalformedToolArgumentsError,
    MuseAPIError, MuseResponseParsingError, ToolExecutionError, UnknownToolError,
)
from backend.agent.orchestrator import MAX_AGENT_STEPS, MuseOrchestrator
from backend.agent.prompts import GRIDPROBE_DEVELOPER_PROMPT
from backend.scenarios.loader import load_scenario
from backend.tools.definitions import get_tool_definitions
from backend.tools.runtime import ScenarioToolRuntime


def tool_call(name: str, call_id: str, arguments: Any = None) -> dict[str, Any]:
    if arguments is None:
        arguments = {"panel_id": "GP-017"}
    return {"id": call_id, "type": "function", "function": {
        "name": name,
        "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
    }}


def response(*calls: dict[str, Any], content: str | None = None, with_usage: bool = True) -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "chatcmpl-scripted", "object": "chat.completion", "created": 1,
        "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if calls else "stop", "message": {
            "role": "assistant", "content": content, "tool_calls": list(calls) or None,
        }}],
        "usage": {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
            "completion_tokens_details": {"reasoning_tokens": 2},
        } if with_usage else None,
    })


def diagnosis(evidence_ids: list[str] | None = None) -> DiagnosisResult:
    """A schema-valid test response, not a measured diagnostic claim."""
    return DiagnosisResult(
        status="NEEDS_MORE_EVIDENCE", likely_fault="unknown", risk_level="UNKNOWN",
        confidence=0.4, evidence_ids=evidence_ids or [],
        reasoning_summary="Scripted test response referencing the supplied measurements.",
        recommended_inspection="Additional inspection by qualified maintenance personnel.",
        missing_evidence=["Additional observations"],
    )


def final_response(evidence_ids: list[str] | None = None) -> ParsedChatCompletion[DiagnosisResult]:
    parsed = diagnosis(evidence_ids)
    data = response(content=parsed.model_dump_json()).model_dump()
    data["choices"][0]["message"]["parsed"] = parsed
    return ParsedChatCompletion[DiagnosisResult].model_validate(data)


class FakeMuseProvider:
    """No SDK client exists. Exhausting the script fails the investigation."""

    def __init__(self, replies: list[Any], final: Any = None) -> None:
        self.replies = iter(replies)
        self.final = final if final is not None else final_response()
        self.requests: list[dict[str, Any]] = []
        self.final_requests: list[dict[str, Any]] = []

    def chat_completion(self, messages: list[Any], *, tools: list[Any] | None = None) -> ChatCompletion:
        self.requests.append({"messages": deepcopy(messages), "tools": deepcopy(tools)})
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def structured_completion(self, messages: list[Any], *, response_format: Any) -> Any:
        # No tools parameter is accepted, so finalization cannot supply tools.
        self.final_requests.append({"messages": deepcopy(messages), "response_format": response_format})
        if isinstance(self.final, Exception):
            raise self.final
        return self.final


@pytest.fixture
def runtime() -> ScenarioToolRuntime:
    case = load_scenario(
        Path(__file__).resolve().parents[1]
        / "demo/scenarios/case_001_connection_overheating.json"
    )
    return ScenarioToolRuntime(case.to_scenario_data(), reliability=0.8)


def test_one_tool_then_separate_finalization(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([
        response(tool_call("calculate_phase_imbalance", "call-1")),
        response(content="Ready to finalize."),
    ], final_response(["EV-001"]))
    result = MuseOrchestrator(provider, runtime).investigate()
    assert len(provider.requests) == 2
    assert len(provider.final_requests) == 1
    assert result.case_id == "CASE-001"
    assert result.panel_id == "GP-017"
    assert result.diagnosis == diagnosis(["EV-001"])
    assert result.termination_reason == "NATURAL_STOP"
    assert result.termination_error is None
    assert len(result.evidence) == 1
    assert [step.kind for step in result.trace] == [
        "MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT", "MODEL_RESPONSE", "MODEL_RESPONSE"
    ]
    assert result.trace[-1].phase == "FINALIZATION"
    assert result.trace[2].evidence_ids_added == ["EV-001"]
    tool_message = provider.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-1"
    assert json.loads(tool_message["content"])["result"]["most_deviant_phase"] == "B"
    assert result.usage.request_count == result.usage.requests_with_usage == 3
    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 15
    assert result.usage.total_tokens == 45
    assert result.usage.reasoning_tokens == 6


def test_initial_request_contains_only_initial_context(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([response(content="No further tools requested.")])
    MuseOrchestrator(provider, runtime).investigate()
    request = provider.requests[0]
    assert request["tools"] == get_tool_definitions()
    messages = request["messages"]
    assert messages[0] == {"role": "developer", "content": GRIDPROBE_DEVELOPER_PROMPT}
    assert messages[1]["role"] == "user"
    initial = json.loads(messages[1]["content"].split("\n", 1)[1])
    assert set(initial) == {"case_id", "panel_id", "initial_snapshot"}
    assert initial["initial_snapshot"]["temperature"] == 78.3
    assert "history" not in initial
    assert "maintenance_context" not in initial
    assert "optional_image" not in initial


def test_case_001_mocked_sequential_investigation(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([
        response(tool_call("calculate_phase_imbalance", "phase")),
        response(tool_call("calculate_temperature_trend", "trend", {"panel_id": "GP-017", "minutes": 60})),
        response(tool_call("get_sensor_history", "current-history", {"panel_id": "GP-017", "sensor": "current_b", "minutes": 60})),
        response(tool_call("get_sensor_history", "voltage-history", {"panel_id": "GP-017", "sensor": "voltage_b", "minutes": 60})),
        response(tool_call("get_maintenance_context", "maintenance")),
        response(content="Collected observations are available for finalization."),
    ], final_response([f"EV-{number:03d}" for number in range(1, 6)]))
    result = MuseOrchestrator(provider, runtime).investigate()
    outputs = [step for step in result.trace if step.kind == "TOOL_RESULT"]
    assert [step.tool_name for step in outputs] == [
        "calculate_phase_imbalance", "calculate_temperature_trend", "get_sensor_history",
        "get_sensor_history", "get_maintenance_context"
    ]
    assert outputs[0].tool_result["imbalance_percent"] == pytest.approx(28.1, abs=0.01)
    assert outputs[0].tool_result["most_deviant_phase"] == "B"
    assert outputs[1].tool_result["temperature_change"] == pytest.approx(32.1)
    assert outputs[1].tool_result["duration_minutes"] == 60
    evidence_ids = [f"EV-{number:03d}" for number in range(1, 6)]
    assert [step.evidence_ids_added for step in outputs] == [[evidence_id] for evidence_id in evidence_ids]
    assert [record.id for record in result.evidence] == evidence_ids
    assert result.diagnosis.evidence_ids == evidence_ids
    assert [record.type.value for record in result.evidence] == [
        "PHASE_IMBALANCE", "TEMPERATURE_TREND", "CURRENT_HISTORY", "VOLTAGE_HISTORY", "MAINTENANCE_NOTE"
    ]
    assert result.usage.request_count == 7
    assert [step.step_number for step in result.trace] == list(range(1, len(result.trace) + 1))
    for request in provider.requests:
        assert request["tools"] == get_tool_definitions()
    final_messages = provider.final_requests[0]["messages"]
    tool_messages = [message for message in final_messages if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "phase", "trend", "current-history", "voltage-history", "maintenance"
    ]
    assert json.loads(final_messages[-1]["content"])["evidence_ledger"] == runtime.evidence_ledger.export()
    assert final_messages[:len(provider.requests[-1]["messages"])] == provider.requests[-1]["messages"]


def test_multiple_tool_calls_in_one_response(runtime: ScenarioToolRuntime) -> None:
    calls = [
        tool_call("get_current_snapshot", "snapshot"),
        tool_call("get_sensor_history", "history", {"panel_id": "GP-017", "sensor": "current_b", "minutes": 30}),
        tool_call("calculate_temperature_trend", "trend", {"panel_id": "GP-017", "minutes": 60}),
    ]
    provider = FakeMuseProvider([response(*calls, content="Request these observations."), response(content="Done.")], final_response(["EV-001", "EV-002"]))
    result = MuseOrchestrator(provider, runtime).investigate()
    messages = provider.requests[1]["messages"]
    assert [message["role"] for message in messages] == ["developer", "user", "assistant", "tool", "tool", "tool"]
    assert messages[2]["tool_calls"] == calls
    assert [message["tool_call_id"] for message in messages[3:]] == ["snapshot", "history", "trend"]
    history = json.loads(messages[4]["content"])["result"]
    assert history["sensor"] == "current_b"
    assert all(set(point) == {"timestamp", "value"} for point in history["points"])
    assert json.loads(messages[4]["content"])["evidence_ids_added"] == ["EV-001"]
    assert json.loads(messages[5]["content"])["evidence_ids_added"] == ["EV-002"]
    assert [step.kind for step in result.trace[:7]] == [
        "MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT", "TOOL_CALL", "TOOL_RESULT", "TOOL_CALL", "TOOL_RESULT"
    ]


@pytest.mark.parametrize("name", ["unknown", "__getattribute__", "initial_context", "inspect_component_image"])
def test_unknown_tool_rejected(runtime: ScenarioToolRuntime, name: str) -> None:
    provider = FakeMuseProvider([response(tool_call(name, "unknown"))])
    with pytest.raises(UnknownToolError):
        MuseOrchestrator(provider, runtime).investigate()
    assert runtime.evidence_ledger.export() == []
    assert provider.final_requests == []


@pytest.mark.parametrize("arguments", [
    "{broken", "[]", "null", "{}", '{"panel_id": 1}',
    '{"panel_id":"GP-017","unexpected":true}',
    '{"panel_id":"GP-017","panel_id":"OTHER"}',
])
def test_malformed_arguments(runtime: ScenarioToolRuntime, arguments: str) -> None:
    provider = FakeMuseProvider([response(tool_call("get_current_snapshot", "invalid", arguments))])
    with pytest.raises(MalformedToolArgumentsError):
        MuseOrchestrator(provider, runtime).investigate()
    assert provider.final_requests == []


@pytest.mark.parametrize("arguments", [
    {"panel_id": "GP-017", "minutes": 0},
    {"panel_id": "GP-017", "minutes": True},
    {"panel_id": "GP-017", "minutes": "60"},
    '{"panel_id":"GP-017","minutes":NaN}',
])
def test_invalid_trend_arguments(runtime: ScenarioToolRuntime, arguments: Any) -> None:
    provider = FakeMuseProvider([response(tool_call("calculate_temperature_trend", "invalid", arguments))])
    with pytest.raises(MalformedToolArgumentsError):
        MuseOrchestrator(provider, runtime).investigate()


def test_entire_batch_validated_before_execution(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([response(
        tool_call("calculate_phase_imbalance", "valid"), tool_call("unknown", "invalid"),
    )])
    with pytest.raises(UnknownToolError):
        MuseOrchestrator(provider, runtime).investigate()
    assert runtime.evidence_ledger.export() == []


@pytest.mark.parametrize("call_ids", [("same", "same"), ("", "other")])
def test_invalid_tool_call_ids(runtime: ScenarioToolRuntime, call_ids: tuple[str, str]) -> None:
    provider = FakeMuseProvider([response(*[
        tool_call("get_current_snapshot", call_id) for call_id in call_ids
    ])])
    with pytest.raises(MalformedToolArgumentsError, match="IDs"):
        MuseOrchestrator(provider, runtime).investigate()


@pytest.mark.parametrize("arguments", [
    {"panel_id": "OTHER"},
    {"panel_id": "GP-017", "minutes": 1},
])
def test_real_tool_execution_failure(runtime: ScenarioToolRuntime, arguments: dict[str, Any]) -> None:
    name = "calculate_temperature_trend" if "minutes" in arguments else "get_current_snapshot"
    provider = FakeMuseProvider([response(tool_call(name, "failed", arguments))])
    with pytest.raises(ToolExecutionError):
        MuseOrchestrator(provider, runtime).investigate()
    assert provider.final_requests == []
    assert runtime.evidence_ledger.export() == []


def test_tool_exception_text_is_not_leaked(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([response(tool_call("get_current_snapshot", "failed"))])
    with patch.object(runtime, "get_current_snapshot", side_effect=RuntimeError("SECRET-TEST-MARKER")):
        with pytest.raises(ToolExecutionError) as exc:
            MuseOrchestrator(provider, runtime).investigate()
    assert "SECRET-TEST-MARKER" not in str(exc.value)
    assert exc.value.__suppress_context__


def test_repeated_request_preserves_single_evidence_record(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([
        response(tool_call("calculate_phase_imbalance", "first")),
        response(tool_call("calculate_phase_imbalance", "repeated")),
        response(content="Done."),
    ], final_response(["EV-001"]))
    result = MuseOrchestrator(provider, runtime).investigate()
    assert [record.id for record in result.evidence] == ["EV-001"]
    outputs = [step for step in result.trace if step.kind == "TOOL_RESULT"]
    assert [step.evidence_ids_added for step in outputs] == [["EV-001"], []]
    assert outputs[0].tool_result == outputs[1].tool_result


def test_max_step_limit_still_finalizes_with_explicit_termination(runtime: ScenarioToolRuntime) -> None:
    assert MAX_AGENT_STEPS == 8
    provider = FakeMuseProvider([
        response(tool_call("calculate_phase_imbalance", f"repeat-{index}"))
        for index in range(MAX_AGENT_STEPS)
    ], final_response(["EV-001"]))
    result = MuseOrchestrator(provider, runtime).investigate()
    assert len(provider.requests) == 8
    assert len(provider.final_requests) == 1
    assert result.usage.request_count == 9
    assert result.termination_reason == "MAX_AGENT_STEPS"
    assert result.termination_error.code == "MAX_AGENT_STEPS"
    assert result.trace[-2].kind == "MAX_STEP_TERMINATION"
    assert result.trace[-2].error == result.termination_error
    assert result.trace[-1].phase == "FINALIZATION"
    assert [record.id for record in result.evidence] == ["EV-001"]
    messages = provider.final_requests[0]["messages"]
    assert "avoid unsupported certainty" in messages[-2]["content"]
    assert json.loads(messages[-1]["content"])["investigation_step_limit_reached"] is True
    assert messages[-3]["role"] == "tool"
    assert messages[-3]["tool_call_id"] == "repeat-7"


def test_natural_stop_on_eighth_turn_is_not_limit_termination(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([
        *[response(tool_call("get_current_snapshot", f"call-{index}")) for index in range(7)],
        response(content="Done."),
    ])
    result = MuseOrchestrator(provider, runtime).investigate()
    assert result.termination_reason == "NATURAL_STOP"
    assert result.termination_error is None


def test_finalization_includes_complete_conversation_and_ledger(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([
        response(tool_call("calculate_phase_imbalance", "phase")), response(content="Ready."),
    ], final_response(["EV-001"]))
    MuseOrchestrator(provider, runtime).investigate()
    request = provider.final_requests[0]
    assert request["response_format"] is DiagnosisResult
    assert "tools" not in request
    messages = request["messages"]
    assert messages[:-3] == provider.requests[1]["messages"]
    assert messages[-3] == {"role": "assistant", "content": "Ready."}
    assert messages[-2]["role"] == "developer"
    assert "DiagnosisResult JSON object" in messages[-2]["content"]
    payload = json.loads(messages[-1]["content"])
    assert payload["evidence_ledger"] == runtime.evidence_ledger.export()
    assert payload["investigation_step_limit_reached"] is False


@pytest.mark.parametrize("field,value", [
    ("status", "INVALID"), ("confidence", 2), ("likely_fault", "invented"),
    ("evidence_ids", "not-a-list"), ("risk_level", "invented"),
])
def test_final_diagnosis_revalidated(runtime: ScenarioToolRuntime, field: str, value: Any) -> None:
    final = final_response()
    # Deliberately bypass construction validation to exercise the orchestrator gate.
    final.choices[0].message.parsed = DiagnosisResult.model_construct(**{
        **diagnosis().model_dump(), field: value,
    })
    provider = FakeMuseProvider([response(content="Ready.")], final)
    with pytest.raises(DiagnosisSchemaError, match="schema"):
        MuseOrchestrator(provider, runtime).investigate()


@pytest.mark.parametrize("content", ["Free-form diagnosis", '{"status":"INVALID"}', diagnosis().model_dump_json()])
def test_unparsed_text_cannot_bypass_validation(runtime: ScenarioToolRuntime, content: str) -> None:
    final = final_response()
    final.choices[0].message.parsed = None
    final.choices[0].message.content = content
    provider = FakeMuseProvider([response(content="Ready.")], final)
    with pytest.raises(DiagnosisSchemaError, match="no parsed"):
        MuseOrchestrator(provider, runtime).investigate()


def test_fabricated_evidence_reference_rejected(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([response(content="Ready.")], final_response(["EV-999"]))
    with pytest.raises(DiagnosisSchemaError, match="absent"):
        MuseOrchestrator(provider, runtime).investigate()


def test_structured_parsing_failure_is_explicit(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([response(content="Ready.")], MuseResponseParsingError("SECRET-TEST-MARKER"))
    with pytest.raises(DiagnosisSchemaError) as exc:
        MuseOrchestrator(provider, runtime).investigate()
    assert "SECRET-TEST-MARKER" not in str(exc.value)


@pytest.mark.parametrize("phase", ["investigation", "finalization"])
def test_provider_failure_is_redacted(runtime: ScenarioToolRuntime, phase: str) -> None:
    error = MuseAPIError("SECRET-TEST-MARKER")
    provider = FakeMuseProvider(
        [error] if phase == "investigation" else [response(content="Ready.")], error,
    )
    with pytest.raises(AgentProviderError) as exc:
        MuseOrchestrator(provider, runtime).investigate()
    assert "SECRET-TEST-MARKER" not in str(exc.value)
    assert exc.value.__suppress_context__


@pytest.mark.parametrize("variant", ["empty", "length", "refusal", "tools"])
def test_invalid_finalization_response(runtime: ScenarioToolRuntime, variant: str) -> None:
    final = final_response()
    if variant == "empty":
        final.choices = []
    elif variant == "length":
        final.choices[0].finish_reason = "length"
    elif variant == "refusal":
        final.choices[0].message.refusal = "Refused."
    else:
        final.choices[0].message.tool_calls = response(tool_call("get_current_snapshot", "unexpected")).choices[0].message.tool_calls
    with pytest.raises(DiagnosisSchemaError):
        MuseOrchestrator(FakeMuseProvider([response(content="Ready.")], final), runtime).investigate()


@pytest.mark.parametrize("variant", ["empty", "length", "refusal", "missing_calls"])
def test_invalid_investigation_response(runtime: ScenarioToolRuntime, variant: str) -> None:
    reply = response(content="Text.")
    if variant == "empty":
        reply.choices = []
    elif variant == "length":
        reply.choices[0].finish_reason = "length"
    elif variant == "refusal":
        reply.choices[0].message.refusal = "Refused."
    else:
        reply.choices[0].finish_reason = "tool_calls"
    with pytest.raises(AgentProviderError):
        MuseOrchestrator(FakeMuseProvider([reply]), runtime).investigate()


def test_no_evaluation_or_image_leakage(runtime: ScenarioToolRuntime) -> None:
    provider = FakeMuseProvider([
        response(tool_call("calculate_phase_imbalance", "phase")), response(content="Ready."),
    ], final_response(["EV-001"]))
    result = MuseOrchestrator(provider, runtime).investigate()
    serialized = json.dumps({
        "requests": provider.requests,
        "final_messages": provider.final_requests[0]["messages"],
        "result": result.model_dump(mode="json"),
    }, allow_nan=False)
    for forbidden in (
        "hidden_ground_truth", "expected_relevant_evidence", "optional_image", "demo/assets/",
        "localized_terminal_visual_anomaly", "stable_voltage",
    ):
        assert forbidden not in serialized
    assert '"history":' not in serialized
    assert "2026-11-03T08:00:00" not in serialized


def test_usage_unavailable_or_partial(runtime: ScenarioToolRuntime) -> None:
    final = final_response()
    final.usage = None
    provider = FakeMuseProvider([response(content="Ready.", with_usage=False)], final)
    result = MuseOrchestrator(provider, runtime).investigate()
    assert result.usage.request_count == 2
    assert result.usage.requests_with_usage == 0
    assert result.usage.input_tokens is None
    assert result.usage.reasoning_tokens is None
    provider = FakeMuseProvider([response(content="Ready.", with_usage=False)], final_response())
    result = MuseOrchestrator(provider, runtime).investigate()
    assert result.usage.request_count == 2
    assert result.usage.requests_with_usage == 1
    assert result.usage.total_tokens == 15
