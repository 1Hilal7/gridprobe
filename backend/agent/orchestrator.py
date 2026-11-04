"""Bounded evidence-seeking orchestration; numerical work stays in tools."""

import json
from copy import deepcopy
from typing import Protocol, TypeVar

from openai.types.chat import (
    ChatCompletion, ChatCompletionAssistantMessageParam, ChatCompletionMessage,
    ChatCompletionMessageParam, ChatCompletionToolMessageParam, ChatCompletionToolParam,
    ParsedChatCompletion,
)
from pydantic import BaseModel, ValidationError

from backend.agent.contracts import DiagnosisResult
from backend.agent.errors import (
    AgentProviderError, DiagnosisSchemaError, MalformedToolArgumentsError,
    MaxAgentStepsError, MuseResponseParsingError, ToolExecutionError, UnknownToolError,
)
from backend.agent.models import AgentErrorInfo, InvestigationResult, ModelUsageSummary, TraceStep
from backend.agent.prompts import GRIDPROBE_DEVELOPER_PROMPT
from backend.tools.definitions import get_tool_definitions
from backend.tools.models import HistoryRequest, PanelRequest, TrendRequest, VisualRequest
from backend.tools.runtime import ScenarioToolRuntime


MAX_AGENT_STEPS = 8
ResponseT = TypeVar("ResponseT", bound=BaseModel)


class InvestigationProvider(Protocol):
    """The MuseProvider interface, also implemented by offline test fakes."""

    def chat_completion(
        self, messages: list[ChatCompletionMessageParam], *,
        tools: list[ChatCompletionToolParam] | None = None,
    ) -> ChatCompletion: ...

    def structured_completion(
        self, messages: list[ChatCompletionMessageParam], *, response_format: type[ResponseT],
    ) -> ParsedChatCompletion[ResponseT]: ...


# A fixed allowlist: no model-supplied name is used for arbitrary attribute access.
_REQUEST_MODELS: dict[str, type[BaseModel]] = {
    "get_current_snapshot": PanelRequest,
    "get_sensor_history": HistoryRequest,
    "calculate_phase_imbalance": PanelRequest,
    "calculate_temperature_trend": TrendRequest,
    "get_maintenance_context": PanelRequest,
    "inspect_component_image": VisualRequest,
}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON property")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite JSON constant")


def _record_usage(response: ChatCompletion, usage: ModelUsageSummary) -> None:
    usage.request_count += 1
    if response.usage is None:
        return
    usage.requests_with_usage += 1
    for target, source in (
        ("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = getattr(response.usage, source, None)
        if value is not None:
            setattr(usage, target, (getattr(usage, target) or 0) + value)
    details = response.usage.completion_tokens_details
    if details is not None and details.reasoning_tokens is not None:
        usage.reasoning_tokens = (usage.reasoning_tokens or 0) + details.reasoning_tokens


def _validate_calls(
    message: ChatCompletionMessage, seen_call_ids: set[str],
) -> list[tuple[str, str, BaseModel]]:
    """Validate an entire batch before any operation runs."""
    validated: list[tuple[str, str, BaseModel]] = []
    for call in message.tool_calls or []:
        if call.type != "function" or call.function.name not in _REQUEST_MODELS:
            raise UnknownToolError("Muse requested an unsupported tool.")
        if not call.id or call.id in seen_call_ids:
            raise MalformedToolArgumentsError("Tool-call IDs must be nonempty and unique.")
        try:
            arguments = json.loads(
                call.function.arguments, object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            request = _REQUEST_MODELS[call.function.name].model_validate(arguments)
        except (ValueError, TypeError, RecursionError):
            raise MalformedToolArgumentsError("Muse supplied malformed tool arguments.") from None
        seen_call_ids.add(call.id)
        validated.append((call.id, call.function.name, request))
    return validated


class MuseOrchestrator:
    """Run one investigation over a caller-owned, investigation-scoped runtime.

    Eight investigation model turns bound repeated requests. Tools in each
    response execute in listed order after the entire batch is validated.
    Runtime caching handles repeated measurements and evidence deduplication.
    The ninth call, if needed, is reserved for tool-free finalization.
    """

    def __init__(self, provider: InvestigationProvider, runtime: ScenarioToolRuntime) -> None:
        self._provider = provider
        self._runtime = runtime

    def investigate(self) -> InvestigationResult:
        context = self._runtime.initial_context()
        conversation: list[ChatCompletionMessageParam] = [
            {"role": "developer", "content": GRIDPROBE_DEVELOPER_PROMPT},
            {"role": "user", "content": (
                "Investigate this active incident using the supplied initial context:\n"
                + context.model_dump_json()
            )},
        ]
        trace: list[TraceStep] = []
        usage = ModelUsageSummary()
        seen_call_ids: set[str] = set()
        limit_error: AgentErrorInfo | None = None

        for _ in range(MAX_AGENT_STEPS):
            try:
                response = self._provider.chat_completion(
                    deepcopy(conversation), tools=get_tool_definitions()
                )
            except Exception:
                raise AgentProviderError("Muse investigation request failed.") from None
            _record_usage(response, usage)
            if len(response.choices) != 1:
                raise AgentProviderError("Muse must return exactly one investigation response.")
            choice = response.choices[0]
            if choice.finish_reason not in ("stop", "tool_calls") or choice.message.refusal:
                raise AgentProviderError("Muse investigation response was incomplete or refused.")
            message = choice.message
            trace.append(TraceStep(
                step_number=len(trace) + 1, kind="MODEL_RESPONSE", assistant_content=message.content,
            ))
            calls = message.tool_calls or []
            if not calls and choice.finish_reason != "stop":
                raise AgentProviderError("Muse tool-call response contained no tool calls.")

            validated = _validate_calls(message, seen_call_ids)
            assistant: ChatCompletionAssistantMessageParam = {
                "role": "assistant", "content": message.content,
            }
            if calls:
                assistant["tool_calls"] = [
                    {"id": call.id, "type": "function", "function": {
                        "name": call.function.name, "arguments": call.function.arguments,
                    }}
                    for call in calls
                ]
            conversation.append(assistant)
            if not calls:
                break

            for call_id, name, request in validated:
                conversation.append(self._execute_tool(call_id, name, request, trace))
        else:
            error = MaxAgentStepsError("The investigation reached MAX_AGENT_STEPS before a natural stop.")
            limit_error = AgentErrorInfo(code=error.code, message=str(error))
            trace.append(TraceStep(
                step_number=len(trace) + 1, kind="MAX_STEP_TERMINATION", error=limit_error,
            ))

        diagnosis = self._finalize(conversation, trace, usage, limit_error is not None)
        return InvestigationResult(
            case_id=context.case_id, panel_id=context.panel_id, trace=trace,
            evidence=self._runtime.evidence_ledger.list_all(), diagnosis=diagnosis, usage=usage,
            termination_reason="MAX_AGENT_STEPS" if limit_error else "NATURAL_STOP",
            termination_error=limit_error,
        )

    def _execute_tool(
        self, call_id: str, name: str, request: BaseModel, trace: list[TraceStep],
    ) -> ChatCompletionToolMessageParam:
        operations = {
            "get_current_snapshot": self._runtime.get_current_snapshot,
            "get_sensor_history": self._runtime.get_sensor_history,
            "calculate_phase_imbalance": self._runtime.calculate_phase_imbalance,
            "calculate_temperature_trend": self._runtime.calculate_temperature_trend,
            "get_maintenance_context": self._runtime.get_maintenance_context,
            "inspect_component_image": self._runtime.inspect_component_image,
        }
        arguments = request.model_dump(mode="json")
        trace.append(TraceStep(
            step_number=len(trace) + 1, kind="TOOL_CALL", tool_name=name,
            tool_call_id=call_id, tool_arguments=arguments,
        ))
        before = {record.id for record in self._runtime.evidence_ledger.list_all()}
        try:
            result = operations[name](**request.model_dump())
            payload = result.model_dump(mode="json")
            added = [
                record.id for record in self._runtime.evidence_ledger.list_all()
                if record.id not in before
            ]
            serialized = json.dumps({"result": payload, "evidence_ids_added": added}, allow_nan=False)
        except Exception:
            raise ToolExecutionError(f"Scenario tool {name} could not complete the request.") from None
        trace.append(TraceStep(
            step_number=len(trace) + 1, kind="TOOL_RESULT", tool_name=name,
            tool_call_id=call_id, tool_arguments=arguments, tool_result=payload,
            evidence_ids_added=added,
        ))
        return {"role": "tool", "tool_call_id": call_id, "content": serialized}

    def _finalize(
        self, conversation: list[ChatCompletionMessageParam], trace: list[TraceStep],
        usage: ModelUsageSummary, limit_reached: bool,
    ) -> DiagnosisResult:
        instructions = (
            "Finalize the investigation. Return only the DiagnosisResult JSON object matching the "
            "supplied response schema. Use the serialized Evidence Ledger below and cite only evidence "
            "IDs present in it. Tools are unavailable during finalization."
        )
        if limit_reached:
            instructions += (
                f" The investigation step limit of {MAX_AGENT_STEPS} was reached before a natural stop. "
                "The step limit does not establish evidence sufficiency; avoid unsupported certainty."
            )
        conversation.extend([
            {"role": "developer", "content": instructions},
            {"role": "user", "content": json.dumps({
                "evidence_ledger": self._runtime.evidence_ledger.export(),
                "investigation_step_limit_reached": limit_reached,
            }, allow_nan=False)},
        ])
        try:
            final = self._provider.structured_completion(
                deepcopy(conversation), response_format=DiagnosisResult,
            )
        except (MuseResponseParsingError, ValidationError):
            raise DiagnosisSchemaError("Muse finalization did not produce a valid DiagnosisResult.") from None
        except Exception:
            raise AgentProviderError("Muse finalization request failed.") from None
        _record_usage(final, usage)
        diagnosis = self._validate_diagnosis(final)
        trace.append(TraceStep(
            step_number=len(trace) + 1, kind="MODEL_RESPONSE", phase="FINALIZATION",
            assistant_content=final.choices[0].message.content,
        ))
        return diagnosis

    def _validate_diagnosis(self, final: ParsedChatCompletion[DiagnosisResult]) -> DiagnosisResult:
        if len(final.choices) != 1:
            raise DiagnosisSchemaError("Muse finalization must return exactly one DiagnosisResult.")
        choice = final.choices[0]
        message = choice.message
        if choice.finish_reason != "stop" or message.refusal or message.tool_calls:
            raise DiagnosisSchemaError("Muse finalization was incomplete, refused, or requested tools.")
        parsed = getattr(message, "parsed", None)
        if not isinstance(parsed, DiagnosisResult):
            raise DiagnosisSchemaError("Muse finalization contained no parsed DiagnosisResult.")
        try:
            # Revalidate even injected/constructed model instances; never use free-form text.
            diagnosis = DiagnosisResult.model_validate(parsed.model_dump(warnings=False))
        except ValidationError:
            raise DiagnosisSchemaError("Muse finalization violated the DiagnosisResult schema.") from None
        known_ids = {record.id for record in self._runtime.evidence_ledger.list_all()}
        if any(evidence_id not in known_ids for evidence_id in diagnosis.evidence_ids):
            raise DiagnosisSchemaError("Muse finalization cited evidence absent from the Evidence Ledger.")
        return diagnosis
