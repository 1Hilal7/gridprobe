"""Lightweight CLI/output checks with no live provider requests."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.agent.contracts import DiagnosisResult
from backend.agent.errors import AgentProviderError
from backend.agent.models import InvestigationResult, ModelUsageSummary, TraceStep
from backend.evidence.ledger import EvidenceLedger
from backend.scenarios.models import ScenarioCase, ScenarioData
from backend.tools.runtime import ScenarioToolRuntime
from scripts import run_investigation


def test_argument_defaults_and_explicit_path(phase_imbalance_scenario_path: Path) -> None:
    default = run_investigation.parse_args([])
    assert default.scenario == run_investigation.DEFAULT_SCENARIO
    assert default.scenario == phase_imbalance_scenario_path
    assert default.reliability == 1.0
    explicit = run_investigation.parse_args(["demo/scenarios/custom.json", "--reliability", "0.8"])
    assert explicit.scenario == Path("demo/scenarios/custom.json")
    assert explicit.reliability == 0.8


@pytest.mark.parametrize("value", ["-1", "1.1", "nan", "inf", "invalid"])
def test_invalid_reliability_argument(value: str) -> None:
    with pytest.raises(SystemExit) as exc:
        run_investigation.parse_args(["--reliability", value])
    assert exc.value.code == 2


@pytest.fixture
def result(phase_imbalance_case: ScenarioCase) -> InvestigationResult:
    data = phase_imbalance_case.to_scenario_data()
    runtime = ScenarioToolRuntime(data, reliability=1.0)
    runtime.calculate_phase_imbalance(data.panel_id)
    return InvestigationResult(
        case_id=data.case_id, panel_id=data.panel_id,
        trace=[
            TraceStep(step_number=1, kind="MODEL_RESPONSE", assistant_content="Requesting a measurement."),
            TraceStep(step_number=2, kind="TOOL_CALL", tool_name="calculate_phase_imbalance",
                      tool_call_id="call-1", tool_arguments={"panel_id": data.panel_id}),
            TraceStep(step_number=3, kind="TOOL_RESULT", tool_name="calculate_phase_imbalance",
                      tool_call_id="call-1", tool_result={"most_deviant_phase": "B"},
                      evidence_ids_added=["EV-001"]),
        ],
        evidence=runtime.evidence_ledger.list_all(),
        diagnosis=DiagnosisResult(
            status="NEEDS_MORE_EVIDENCE", likely_fault="unknown", risk_level="UNKNOWN", confidence=0.0,
            evidence_ids=["EV-001"], reasoning_summary="Scripted output formatting test.",
            recommended_inspection="Qualified inspection with additional observations.", missing_evidence=[],
        ),
        usage=ModelUsageSummary(request_count=2, requests_with_usage=2, total_tokens=30),
        termination_reason="NATURAL_STOP",
    )


@pytest.mark.parametrize("key", ["PRIVATE-TEST-CREDENTIAL", 'PRIVATE-TEST-"KEY\\'])
def test_readable_output_and_secret_redaction(
    result: InvestigationResult, monkeypatch: pytest.MonkeyPatch, key: str,
) -> None:
    monkeypatch.setenv("META_API_KEY", key)
    result.trace[0].assistant_content = key
    result.diagnosis.reasoning_summary = key
    text = run_investigation.format_result(result)
    for expected in ("STEP 1 — MODEL", "STEP 2 — TOOL CALL", "STEP 3 — TOOL RESULT",
                     "EVIDENCE", "EV-001", "FINAL DIAGNOSIS", "TOKEN USAGE", '"total_tokens": 30'):
        assert expected in text
    assert "[REDACTED]" in text
    assert key not in text
    assert json.dumps(key)[1:-1] not in text
    for forbidden in ("PRIVATE-TEST-CREDENTIAL", "hidden_ground_truth", "expected_relevant_evidence", "optional_image"):
        assert forbidden not in text


def test_injected_ledger_must_be_empty(result: InvestigationResult, phase_imbalance_case: ScenarioCase) -> None:
    data = phase_imbalance_case.to_scenario_data()
    ledger = EvidenceLedger()
    ledger.add(result.evidence[0])
    with pytest.raises(ValueError, match="empty evidence ledger"):
        ScenarioToolRuntime(data, reliability=1.0, evidence_ledger=ledger)


def test_unavailable_usage(result: InvestigationResult) -> None:
    result.usage = ModelUsageSummary(request_count=2)
    assert "Unavailable (2 model requests)." in run_investigation.format_result(result)


def test_cli_wiring_uses_projection_and_explicit_ledger(
    result: InvestigationResult, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    # Only the outer orchestrator/provider are stubbed; script/runtime contain no mocks.
    provider_factory = MagicMock()
    monkeypatch.setattr(run_investigation, "MuseProvider", provider_factory)
    orchestrator_factory = MagicMock()
    orchestrator_factory.return_value.investigate.return_value = result
    monkeypatch.setattr(run_investigation, "MuseOrchestrator", orchestrator_factory)
    runtime_factory = MagicMock(wraps=ScenarioToolRuntime)
    monkeypatch.setattr(run_investigation, "ScenarioToolRuntime", runtime_factory)
    assert run_investigation.main([]) == 0
    assert type(runtime_factory.call_args.args[0]) is ScenarioData
    assert isinstance(runtime_factory.call_args.kwargs["evidence_ledger"], EvidenceLedger)
    assert orchestrator_factory.call_args.args[1].evidence_ledger is runtime_factory.call_args.kwargs["evidence_ledger"]
    assert orchestrator_factory.call_args.args[0] is provider_factory.return_value.__enter__.return_value
    orchestrator_factory.return_value.investigate.assert_called_once_with()
    provider_factory.return_value.__exit__.assert_called_once()
    output = capsys.readouterr()
    assert "INVESTIGATION CASE-002 / GP-017" in output.out
    assert "FINAL DIAGNOSIS" in output.out
    assert "hidden_ground_truth" not in output.out
    assert "expected_relevant_evidence" not in output.out
    assert output.err == ""


def test_invalid_scenario_does_not_print_private_validation_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('{"hidden_ground_truth":"PRIVATE-LABEL","expected_relevant_evidence":["PRIVATE-EXPECTED"]}', encoding="utf-8")
    factory = MagicMock()
    monkeypatch.setattr(run_investigation, "MuseProvider", factory)
    assert run_investigation.main([str(path)]) == 1
    factory.assert_not_called()
    output = capsys.readouterr()
    assert "Cannot load scenario" in output.err
    assert output.out == ""
    for forbidden in ("hidden_ground_truth", "expected_relevant_evidence", "PRIVATE-LABEL", "PRIVATE-EXPECTED"):
        assert forbidden not in output.err


def test_provider_error_does_not_print_secret(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("META_API_KEY", "PRIVATE-TEST-CREDENTIAL")
    factory = MagicMock(side_effect=AgentProviderError("Failure PRIVATE-TEST-CREDENTIAL"))
    monkeypatch.setattr(run_investigation, "MuseProvider", factory)
    assert run_investigation.main([]) == 1
    factory.assert_called_once_with()
    output = capsys.readouterr()
    assert "Cannot load scenario" not in output.err
    assert "Investigation failed:" in output.err
    assert "PRIVATE-TEST-CREDENTIAL" not in output.err
    assert "[REDACTED]" in output.err
