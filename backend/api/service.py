"""Product boundary around the unchanged scenario runtime and Muse agent."""

import os
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from backend.agent.errors import (
    AgentProviderError, DiagnosisSchemaError, GridProbeAgentError, MuseAPIError, MuseConfigurationError,
)
from backend.agent.models import InvestigationResult, TraceStep
from backend.agent.orchestrator import MuseOrchestrator
from backend.agent.provider import MuseProvider
from backend.api.config import product_pricing
from backend.api.models import InvestigationCase, InvestigationResponse, PublicTraceStep, ScenarioSummary
from backend.evaluation.scoring import estimate_api_cost
from backend.evidence.ledger import EvidenceLedger
from backend.scenarios.loader import DEFAULT_SCENARIO_DIRECTORY, load_scenario
from backend.scenarios.models import ScenarioData
from backend.tools.runtime import ScenarioToolRuntime


PRIMARY_SCENARIOS = {
    "CASE-001": "case_001_connection_overheating.json",
    "CASE-002": "case_002_phase_imbalance.json",
    "CASE-003": "case_003_overload.json",
    "CASE-004": "case_004_normal_or_insufficient.json",
}
PublicT = TypeVar("PublicT", bound=BaseModel)


class ProductAPIError(Exception):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False) -> None:
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def _load_primary(case_id: str) -> ScenarioData:
    filename = PRIMARY_SCENARIOS.get(case_id)
    if filename is None:
        raise ProductAPIError(404, "CASE_NOT_FOUND", "This demo case is not available. Choose a listed case.")
    try:
        case = load_scenario(DEFAULT_SCENARIO_DIRECTORY / filename)
        if case.case_id != case_id:
            raise ValueError("Scenario identity mismatch")
        return case.to_scenario_data()
    except Exception:
        raise ProductAPIError(500, "SCENARIO_UNAVAILABLE", "The demo scenario could not be loaded.") from None


def _image_available(data: ScenarioData) -> bool:
    if data.optional_image is None:
        return False
    root = DEFAULT_SCENARIO_DIRECTORY.parents[1]
    path = (root / data.optional_image).resolve()
    return path.is_relative_to(root / "demo/assets") and path.is_file()


def _summary(data: ScenarioData) -> ScenarioSummary:
    return ScenarioSummary(
        case_id=data.case_id, panel_id=data.panel_id, initial_snapshot=data.initial_snapshot,
        image_available=_image_available(data),
    )


def _public_trace(step: TraceStep) -> PublicTraceStep:
    summaries = {
        "MODEL_RESPONSE": "Agent reviewed the available observations.",
        "TOOL_CALL": "Requested a measurement or recorded context.",
        "TOOL_RESULT": "Tool returned observations for the investigation.",
        "MAX_STEP_TERMINATION": "Investigation step limit reached; finalizing with the collected evidence.",
    }
    summary = summaries[step.kind]
    if step.phase == "FINALIZATION":
        summary = "Structured diagnosis validated against the evidence ledger."
    # Private assistant_content is deliberately never copied to the product API.
    return PublicTraceStep(
        step_number=step.step_number, kind=step.kind, phase=step.phase, summary=summary,
        tool_name=step.tool_name, tool_call_id=step.tool_call_id,
        tool_arguments=step.tool_arguments, tool_result=step.tool_result,
        evidence_ids_added=step.evidence_ids_added,
    )


def _redact(value: object) -> object:
    """Final defense for credentials and private annotation keys in public output."""
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items() if key not in {
            "hidden_ground_truth", "expected_relevant_evidence", "api_key", "META_API_KEY",
        }}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        key = os.environ.get("META_API_KEY")
        return value.replace(key, "[REDACTED]") if key else value
    return value


def _safe_model(model: PublicT) -> PublicT:
    return type(model).model_validate(_redact(model.model_dump(mode="json")))


def list_demo_scenarios() -> list[ScenarioSummary]:
    return [_safe_model(_summary(_load_primary(case_id))) for case_id in PRIMARY_SCENARIOS]


def run_investigation(case_id: str) -> InvestigationResponse:
    data = _load_primary(case_id)
    try:
        pricing = product_pricing()
    except ValueError:
        raise ProductAPIError(503, "PRICING_NOT_CONFIGURED", "Check the server's USD token pricing configuration.") from None
    try:
        ledger = EvidenceLedger()
        runtime = ScenarioToolRuntime(data, reliability=1.0, evidence_ledger=ledger)
        with MuseProvider() as provider:
            result = MuseOrchestrator(provider, runtime).investigate()
            model = provider.config.model
        # Validate the transport boundary too, including injected test providers.
        result = InvestigationResult.model_validate(result.model_dump())
        if (result.case_id, result.panel_id) != (data.case_id, data.panel_id):
            raise DiagnosisSchemaError("Investigation identity mismatch")
        response = InvestigationResponse(
            case=InvestigationCase(**_summary(data).model_dump(), history=data.history),
            trace=[_public_trace(step) for step in result.trace], evidence=result.evidence,
            diagnosis=result.diagnosis, usage=result.usage, estimated_cost_usd=estimate_api_cost(result.usage, pricing),
            cost_is_partial=(result.usage.requests_with_usage != result.usage.request_count
                             or result.usage.input_tokens is None or result.usage.output_tokens is None),
            model=model, termination_reason=result.termination_reason,
        )
        return _safe_model(response)
    except MuseConfigurationError:
        raise ProductAPIError(
            503, "MODEL_NOT_CONFIGURED", "Model access is not configured. Set META_API_KEY and check META_MODEL on the server.",
        ) from None
    except (DiagnosisSchemaError, ValidationError):
        raise ProductAPIError(502, "INVALID_DIAGNOSIS", "The model did not return a valid, evidence-backed diagnosis. Retry the investigation.", retryable=True) from None
    except (AgentProviderError, MuseAPIError):
        raise ProductAPIError(502, "PROVIDER_UNAVAILABLE", "The model provider could not complete the investigation. Please retry.", retryable=True) from None
    except GridProbeAgentError:
        raise ProductAPIError(502, "INVESTIGATION_FAILED", "The investigation could not complete its tool operations. Please retry.", retryable=True) from None
    except Exception:
        raise ProductAPIError(500, "INVESTIGATION_FAILED", "The investigation could not be completed. Please retry.", retryable=True) from None
