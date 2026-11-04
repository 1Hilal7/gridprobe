"""Pure metric tests and injected-provider evaluation; no network access."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion, ParsedChatCompletion
from pydantic import ValidationError

from backend.agent.contracts import DiagnosisResult
from backend.agent.errors import (
    AgentProviderError, DiagnosisSchemaError, MalformedToolArgumentsError,
    ToolExecutionError, UnknownToolError,
)
from backend.api.config import product_pricing
from backend.agent.models import InvestigationResult, ModelUsageSummary, TraceStep
from backend.evaluation.config import EvaluationConfigurationError, PricingConfig
from backend.evaluation.models import EvaluationReport
from backend.evaluation.runner import EvaluationDatasetError, evaluate_cases, load_evaluation_cases, select_evaluation_cases
from backend.evaluation.scoring import aggregate_metrics, estimate_api_cost, score_investigation
from backend.scenarios.loader import load_scenarios
from backend.scenarios.models import ScenarioCase
from backend.tools.runtime import ScenarioToolRuntime


@pytest.fixture
def cases() -> list[ScenarioCase]:
    return load_scenarios()


def make_result(
    case: ScenarioCase, *, status: str = "DIAGNOSIS_READY", fault: str = "unknown",
    references: list[str] | None = None, tools: int = 1, usage: ModelUsageSummary | None = None,
) -> InvestigationResult:
    runtime = ScenarioToolRuntime(case.to_scenario_data(), reliability=1.0)
    runtime.calculate_phase_imbalance(case.panel_id)
    return InvestigationResult(
        case_id=case.case_id, panel_id=case.panel_id,
        trace=[
            *[TraceStep(step_number=i + 1, kind="TOOL_CALL", tool_name="get_current_snapshot") for i in range(tools)],
            TraceStep(step_number=tools + 1, kind="TOOL_RESULT"),
            TraceStep(step_number=tools + 2, kind="MODEL_RESPONSE"),
        ],
        evidence=runtime.evidence_ledger.list_all(),
        diagnosis=DiagnosisResult(
            status=status, likely_fault=fault, risk_level="UNKNOWN", confidence=0.0,
            evidence_ids=["EV-001"] if references is None else references,
            reasoning_summary="Scripted scoring fixture.", recommended_inspection="Qualified inspection.", missing_evidence=[],
        ),
        usage=usage if usage is not None else ModelUsageSummary(
            request_count=2, requests_with_usage=2, input_tokens=100, output_tokens=50,
            total_tokens=150, reasoning_tokens=20,
        ),
        termination_reason="NATURAL_STOP",
    )


@pytest.mark.parametrize("case_index", [0, 1, 2])
@pytest.mark.parametrize("status,correct_label,expected", [
    ("DIAGNOSIS_READY", True, True), ("DIAGNOSIS_READY", False, False),
    ("NEEDS_MORE_EVIDENCE", True, False), ("NO_ACTIONABLE_DIAGNOSIS", True, False),
])
def test_exact_diagnosis_scoring(cases: list[ScenarioCase], case_index: int, status: str, correct_label: bool, expected: bool) -> None:
    case = cases[case_index]
    result = make_result(case, status=status, fault=case.hidden_ground_truth if correct_label else "unknown")
    scored = score_investigation(case, result)
    assert scored.exact_diagnosis_correct is expected
    assert scored.abstention_correct is None
    metrics = aggregate_metrics([scored], PricingConfig())
    assert metrics.diagnosis_accuracy == int(expected)
    assert metrics.correct_abstention_rate is None


@pytest.mark.parametrize("status,abstention,unnecessary", [
    ("NEEDS_MORE_EVIDENCE", True, False), ("NO_ACTIONABLE_DIAGNOSIS", True, False),
    ("DIAGNOSIS_READY", False, True),
])
def test_abstention_and_unnecessary_diagnosis(cases: list[ScenarioCase], status: str, abstention: bool, unnecessary: bool) -> None:
    scored = score_investigation(cases[3], make_result(cases[3], status=status))
    assert scored.exact_diagnosis_correct is None
    assert scored.abstention_correct is abstention
    assert scored.unnecessary_diagnosis is unnecessary
    metrics = aggregate_metrics([scored], PricingConfig())
    assert metrics.correct_abstention_rate == int(abstention)
    assert metrics.unsafe_or_unnecessary_diagnosis_rate == int(unnecessary)
    assert metrics.diagnosis_accuracy is None


def test_micro_averaged_evidence_validity_and_tool_call_average(cases: list[ScenarioCase]) -> None:
    scored = [
        score_investigation(cases[0], make_result(cases[0], references=["EV-001", "missing", "EV-001"], tools=3)),
        score_investigation(cases[1], make_result(cases[1], references=["EV-001"], tools=1)),
    ]
    metrics = aggregate_metrics(scored, PricingConfig())
    assert metrics.valid_evidence_references == 3
    assert metrics.total_evidence_references == 4
    assert metrics.evidence_reference_validity == 75.0
    assert metrics.average_tool_calls == 2.0
    assert metrics.average_request_count == 2.0


def test_no_citations_is_unavailable_validity(cases: list[ScenarioCase]) -> None:
    scored = score_investigation(cases[0], make_result(cases[0], references=[]))
    assert aggregate_metrics([scored], PricingConfig()).evidence_reference_validity is None


def test_usage_and_cost_aggregation_do_not_double_charge_reasoning(cases: list[ScenarioCase]) -> None:
    scored = [score_investigation(case, make_result(case)) for case in cases[:2]]
    # Synthetic prices verify arithmetic; these are not claimed Meta prices.
    pricing = PricingConfig(input_price_per_million=2, output_price_per_million=10)
    metrics = aggregate_metrics(scored, pricing)
    assert metrics.usage.input_tokens == 200
    assert metrics.usage.output_tokens == 100
    assert metrics.usage.reasoning_tokens == 40
    assert metrics.usage.total_tokens == 300
    assert metrics.usage.request_count == 4
    assert metrics.usage.requests_with_usage == 4
    assert metrics.usage_complete
    assert metrics.estimated_api_cost == pytest.approx(0.0014)
    assert metrics.cost_is_partial is False


def test_missing_usage_and_prices_are_not_reported_as_zero(cases: list[ScenarioCase]) -> None:
    empty = score_investigation(cases[0], make_result(cases[0], usage=ModelUsageSummary(request_count=2)))
    metrics = aggregate_metrics([empty], PricingConfig())
    assert metrics.usage.input_tokens is None
    assert metrics.estimated_api_cost is None
    assert metrics.usage_complete is False
    known = score_investigation(cases[1], make_result(cases[1]))
    partial = aggregate_metrics([empty, known], PricingConfig(input_price_per_million=2, output_price_per_million=10))
    assert partial.usage.input_tokens == 100
    assert partial.estimated_api_cost == pytest.approx(0.0007)
    assert partial.cost_is_partial is True
    assert partial.average_request_count == 2


def test_zero_configured_prices_are_distinct_from_missing_prices() -> None:
    usage = ModelUsageSummary(input_tokens=100, output_tokens=50, reasoning_tokens=20)
    assert estimate_api_cost(usage, PricingConfig(input_price_per_million=None, output_price_per_million=None)) is None
    assert estimate_api_cost(usage, PricingConfig(input_price_per_million=0, output_price_per_million=0)) == 0


def test_pricing_environment_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_INPUT_PRICE_PER_MILLION", "2")
    monkeypatch.setenv("META_OUTPUT_PRICE_PER_MILLION", "10")
    monkeypatch.setenv("META_PRICE_CURRENCY", "USD")
    assert PricingConfig.from_env() == PricingConfig(input_price_per_million=2, output_price_per_million=10)
    monkeypatch.delenv("META_INPUT_PRICE_PER_MILLION")
    with pytest.raises(EvaluationConfigurationError):
        PricingConfig.from_env()


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_invalid_price_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        PricingConfig(input_price_per_million=value, output_price_per_million=1)


def stop_response() -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "test", "object": "chat.completion", "created": 1, "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Finalize."}}],
    })


def abstention_response() -> ParsedChatCompletion[DiagnosisResult]:
    result = DiagnosisResult(
        status="NEEDS_MORE_EVIDENCE", likely_fault="unknown", risk_level="UNKNOWN", confidence=0,
        evidence_ids=[], reasoning_summary="Scripted provider response.", recommended_inspection="Qualified inspection.",
        missing_evidence=["Additional observations"],
    )
    payload = stop_response().model_dump()
    payload["choices"][0]["message"].update(content=result.model_dump_json(), parsed=result.model_dump())
    return ParsedChatCompletion[DiagnosisResult].model_validate(payload)


def test_injected_provider_only_receives_projected_case_data(cases: list[ScenarioCase]) -> None:
    provider = MagicMock()
    provider.chat_completion.side_effect = lambda *args, **kwargs: stop_response()
    provider.structured_completion.side_effect = lambda *args, **kwargs: abstention_response()
    report = evaluate_cases(cases, provider, pricing=PricingConfig())
    assert report.metrics.case_count == 4
    assert report.metrics.completed_case_count == 4
    assert report.metrics.diagnosis_accuracy == 0
    assert report.metrics.correct_abstention_rate == 1
    for call in provider.chat_completion.call_args_list:
        initial = json.loads(call.args[0][1]["content"].split("\n", 1)[1])
        assert set(initial) == {"case_id", "panel_id", "initial_snapshot"}
    serialized = str(provider.mock_calls)
    assert "hidden_ground_truth" not in serialized
    assert "expected_relevant_evidence" not in serialized
    assert "demo/assets" not in serialized


def test_failed_cases_remain_in_scoring_denominators_and_errors_are_redacted(cases: list[ScenarioCase]) -> None:
    provider = MagicMock()
    provider.chat_completion.side_effect = AgentProviderError("PRIVATE-TEST-CREDENTIAL")
    report = evaluate_cases(cases, provider, pricing=PricingConfig())
    assert report.metrics.failed_case_count == 4
    assert report.metrics.diagnosis_accuracy == 0
    assert report.metrics.correct_abstention_rate == 0
    assert report.metrics.average_tool_calls is None
    assert report.metrics.average_request_count is None
    assert all(case.investigation is None and case.error is not None for case in report.cases)
    assert "PRIVATE-TEST-CREDENTIAL" not in report.model_dump_json()


def test_report_roundtrip_serialization(cases: list[ScenarioCase]) -> None:
    provider = MagicMock()
    provider.chat_completion.return_value = stop_response()
    provider.structured_completion.return_value = abstention_response()
    report = evaluate_cases(cases, provider, pricing=PricingConfig(), model="muse-spark-1.3")
    assert EvaluationReport.model_validate_json(report.model_dump_json()) == report
    assert json.loads(json.dumps(report.model_dump(mode="json"), allow_nan=False))["metrics"]["case_count"] == 4


def test_loader_excludes_previous_report_and_rejects_duplicate_ids(tmp_path: Path, cases: list[ScenarioCase]) -> None:
    for index, case in enumerate(cases[:2]):
        (tmp_path / f"case_{index}.json").write_text(case.model_dump_json())
    (tmp_path / "results.json").write_text('{"not_a_scenario": true}')
    assert load_evaluation_cases(tmp_path) == cases[:2]
    (tmp_path / "duplicate.json").write_text(cases[0].model_dump_json())
    with pytest.raises(EvaluationDatasetError, match="duplicate"):
        load_evaluation_cases(tmp_path)


def test_empty_dataset_rejected(tmp_path: Path) -> None:
    with pytest.raises(EvaluationDatasetError):
        load_evaluation_cases(tmp_path)


def test_mismatched_result_identity_rejected(cases: list[ScenarioCase]) -> None:
    with pytest.raises(ValueError, match="identity"):
        score_investigation(cases[0], make_result(cases[1]))


def test_standard_pricing_defaults_match_product_api(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("META_INPUT_PRICE_PER_MILLION", "META_OUTPUT_PRICE_PER_MILLION", "META_PRICE_CURRENCY"):
        monkeypatch.delenv(variable, raising=False)
    pricing = PricingConfig.from_env()
    assert pricing.input_price_per_million == 1.25
    assert pricing.output_price_per_million == 4.25
    assert pricing.currency == "USD"
    assert pricing == product_pricing() == PricingConfig()
    usage = ModelUsageSummary(input_tokens=1_000_000, output_tokens=2_000_000, reasoning_tokens=1_000_000)
    assert estimate_api_cost(usage, pricing) == 9.75
    monkeypatch.setenv("META_INPUT_PRICE_PER_MILLION", "")
    monkeypatch.setenv("META_OUTPUT_PRICE_PER_MILLION", "")
    assert PricingConfig.from_env() == pricing


def test_retry_is_opt_in_and_bounded_once(cases: list[ScenarioCase]) -> None:
    provider = MagicMock()
    provider.chat_completion.side_effect = AgentProviderError("PRIVATE-RETRY-CREDENTIAL")
    retry = MagicMock()
    report = evaluate_cases(cases[:1], provider, pricing=PricingConfig(), retry_provider_failures=True, on_retry=retry)
    assert provider.chat_completion.call_count == 2
    provider.structured_completion.assert_not_called()
    retry.assert_called_once_with(cases[0].case_id)
    assert report.cases[0].attempt_count == 2
    assert [error.code for error in report.cases[0].attempt_errors] == ["PROVIDER_FAILED", "PROVIDER_FAILED"]
    assert report.cases[0].error.code == "PROVIDER_FAILED"
    assert "PRIVATE-RETRY-CREDENTIAL" not in report.model_dump_json()
    provider.reset_mock()
    evaluate_cases(cases[:1], provider, pricing=PricingConfig())
    assert provider.chat_completion.call_count == 1


def test_successful_retry_uses_fresh_context_and_deduplicated_new_ledger(cases: list[ScenarioCase]) -> None:
    case = cases[1]
    tool_data = stop_response().model_dump()
    tool_data["choices"][0]["finish_reason"] = "tool_calls"
    tool_data["choices"][0]["message"].update(content=None, tool_calls=[{
        "id": "same-id-in-fresh-investigation", "type": "function", "function": {
            "name": "calculate_phase_imbalance", "arguments": json.dumps({"panel_id": case.panel_id}),
        },
    }])
    tool_response = ChatCompletion.model_validate(tool_data)
    provider = MagicMock()
    provider.chat_completion.side_effect = [
        tool_response, AgentProviderError("private failure"), tool_response, stop_response(),
    ]
    final = abstention_response()
    final.choices[0].message.parsed.evidence_ids = ["EV-001"]
    final.choices[0].message.content = final.choices[0].message.parsed.model_dump_json()
    provider.structured_completion.return_value = final
    report = evaluate_cases([case], provider, pricing=PricingConfig(), retry_provider_failures=True)
    assert report.metrics.completed_case_count == 1
    assert report.cases[0].attempt_count == 2
    assert report.cases[0].error is None
    assert [record.id for record in report.cases[0].investigation.evidence] == ["EV-001"]
    assert report.cases[0].attempt_errors[0].code == "PROVIDER_FAILED"
    first = provider.chat_completion.call_args_list[0].args[0]
    repeated = provider.chat_completion.call_args_list[2].args[0]
    assert first == repeated
    initial = json.loads(repeated[1]["content"].split("\n", 1)[1])
    assert set(initial) == {"case_id", "panel_id", "initial_snapshot"}
    assert "hidden_ground_truth" not in str(provider.mock_calls)
    assert "expected_relevant_evidence" not in str(provider.mock_calls)


@pytest.mark.parametrize("error", [
    DiagnosisSchemaError("private"), UnknownToolError("private"),
    MalformedToolArgumentsError("private"), ToolExecutionError("private"), ValueError("private"),
])
def test_non_provider_failures_are_not_retried(cases: list[ScenarioCase], error: Exception) -> None:
    retry = MagicMock()
    with patch("backend.evaluation.runner.MuseOrchestrator") as orchestrator:
        orchestrator.return_value.investigate.side_effect = error
        report = evaluate_cases(cases[:1], MagicMock(), pricing=PricingConfig(), retry_provider_failures=True, on_retry=retry)
        orchestrator.return_value.investigate.assert_called_once_with()
    retry.assert_not_called()
    assert report.cases[0].attempt_count == 1
    assert report.cases[0].investigation is None
    assert report.cases[0].error.code != "PROVIDER_FAILED"


def test_retry_followed_by_schema_failure_stops(cases: list[ScenarioCase]) -> None:
    with patch("backend.evaluation.runner.MuseOrchestrator") as orchestrator:
        orchestrator.return_value.investigate.side_effect = [AgentProviderError("private"), DiagnosisSchemaError("private")]
        report = evaluate_cases(cases[:1], MagicMock(), pricing=PricingConfig(), retry_provider_failures=True)
        assert orchestrator.return_value.investigate.call_count == 2
    assert report.cases[0].error.code == "DIAGNOSIS_SCHEMA_FAILED"
    assert report.cases[0].attempt_count == 2


def test_retry_usage_and_cost_remain_explicitly_partial(cases: list[ScenarioCase]) -> None:
    with patch("backend.evaluation.runner.MuseOrchestrator") as orchestrator:
        result = make_result(cases[0])
        orchestrator.return_value.investigate.side_effect = [AgentProviderError("private"), result]
        report = evaluate_cases(cases[:1], MagicMock(), pricing=PricingConfig(), retry_provider_failures=True)
    assert report.metrics.usage_complete is False
    assert report.metrics.cost_is_partial is True
    assert report.metrics.usage.request_count == result.usage.request_count
    assert report.metrics.estimated_api_cost == pytest.approx((100 * 1.25 + 50 * 4.25) / 1_000_000)


def test_case_selection_preserves_order_and_deduplicates(cases: list[ScenarioCase]) -> None:
    selected = select_evaluation_cases(cases, [cases[1].case_id, cases[0].case_id, cases[1].case_id])
    assert selected == cases[:2]
    assert select_evaluation_cases(cases, None) == cases
    with pytest.raises(EvaluationDatasetError):
        select_evaluation_cases(cases, ["UNAVAILABLE"])
