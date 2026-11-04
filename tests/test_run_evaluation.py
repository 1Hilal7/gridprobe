"""Live CLI wiring through a mocked MuseProvider; reports stay in tmp_path."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from openai.types.chat import ChatCompletion, ParsedChatCompletion

from backend.agent.contracts import DiagnosisResult
from backend.agent.errors import MuseAPIError, MuseConfigurationError
from backend.evaluation.models import EvaluationReport
from scripts import run_evaluation


@pytest.fixture
def provider_factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    for variable in ("META_INPUT_PRICE_PER_MILLION", "META_OUTPUT_PRICE_PER_MILLION", "META_PRICE_CURRENCY"):
        monkeypatch.delenv(variable, raising=False)
    diagnosis = DiagnosisResult(
        status="NEEDS_MORE_EVIDENCE", likely_fault="unknown", risk_level="UNKNOWN", confidence=0,
        evidence_ids=[], reasoning_summary="Scripted test response.", recommended_inspection="Qualified inspection.",
        missing_evidence=["Additional observations"],
    )
    payload = {
        "id": "test", "created": 1, "model": "muse-spark-1.3", "object": "chat.completion",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Finalize."}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                  "completion_tokens_details": {"reasoning_tokens": 2}},
    }
    factory = MagicMock()
    provider = factory.return_value.__enter__.return_value
    provider.config.model = "muse-spark-1.3"
    provider.chat_completion.return_value = ChatCompletion.model_validate(payload)
    payload["choices"][0]["message"].update(parsed=diagnosis.model_dump(), content=diagnosis.model_dump_json())
    provider.structured_completion.return_value = ParsedChatCompletion[DiagnosisResult].model_validate(payload)
    monkeypatch.setattr(run_evaluation, "MuseProvider", factory)
    return factory


def test_default_cli_arguments() -> None:
    args = run_evaluation.parse_args([])
    assert args.cases_dir == run_evaluation.DEFAULT_EVALUATION_DIRECTORY
    assert args.output is None
    assert args.case_ids is None
    assert run_evaluation._output_path(args, []) == run_evaluation.DEFAULT_REPORT_PATH
    assert args.reliability == 1.0


def test_mocked_live_evaluation_writes_real_runner_report(
    tmp_path: Path, provider_factory: MagicMock, capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "results.json"
    assert run_evaluation.main(["--output", str(path)]) == 0
    report = EvaluationReport.model_validate_json(path.read_text())
    assert report.model == "muse-spark-1.3"
    assert report.metrics.case_count == report.metrics.completed_case_count == 8
    assert report.metrics.correct_abstention_rate == 1
    assert report.metrics.diagnosis_accuracy == 0
    assert report.metrics.average_request_count == 2
    assert report.metrics.usage.total_tokens == 240
    assert report.metrics.estimated_api_cost == pytest.approx(0.00054)
    provider = provider_factory.return_value.__enter__.return_value
    assert provider.chat_completion.call_count == 8
    assert provider.structured_completion.call_count == 8
    assert provider_factory.return_value.__exit__.call_count == 1
    output = capsys.readouterr()
    assert "AGGREGATE METRICS" in output.out
    assert all(f"EVAL-{number:03d}:" in output.out for number in range(1, 9))
    assert output.err == ""


def test_configured_cost_and_secret_redaction(
    tmp_path: Path, provider_factory: MagicMock, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("META_API_KEY", "PRIVATE-LIVE-TEST-KEY")
    monkeypatch.setenv("META_INPUT_PRICE_PER_MILLION", "2")
    monkeypatch.setenv("META_OUTPUT_PRICE_PER_MILLION", "10")
    final = provider_factory.return_value.__enter__.return_value.structured_completion.return_value
    final.choices[0].message.parsed.reasoning_summary = "PRIVATE-LIVE-TEST-KEY"
    final.choices[0].message.content = final.choices[0].message.parsed.model_dump_json()
    path = tmp_path / "results.json"
    assert run_evaluation.main(["--output", str(path)]) == 0
    serialized = path.read_text()
    report = EvaluationReport.model_validate_json(serialized)
    assert report.metrics.estimated_api_cost == pytest.approx(0.00112)
    assert report.metrics.cost_is_partial is False
    output = capsys.readouterr()
    assert "PRIVATE-LIVE-TEST-KEY" not in output.out + output.err + serialized
    assert "[REDACTED]" in serialized


def test_provider_failures_produce_error_entries_not_fake_diagnoses(
    tmp_path: Path, provider_factory: MagicMock, capsys: pytest.CaptureFixture[str],
) -> None:
    provider_factory.return_value.__enter__.return_value.chat_completion.side_effect = MuseAPIError("PRIVATE-TEST-KEY")
    path = tmp_path / "results.json"
    assert run_evaluation.main(["--output", str(path)]) == 1
    report = EvaluationReport.model_validate_json(path.read_text())
    assert report.metrics.failed_case_count == 8
    assert provider_factory.return_value.__enter__.return_value.chat_completion.call_count == 16
    assert all(case.attempt_count == 2 for case in report.cases)
    assert all(case.investigation is None and case.error is not None for case in report.cases)
    output = capsys.readouterr()
    assert "PRIVATE-TEST-KEY" not in output.out + output.err + path.read_text()
    assert output.out.count("retrying case once (attempt 2/2)") == 8


def test_bad_dataset_never_constructs_provider(tmp_path: Path, provider_factory: MagicMock) -> None:
    assert run_evaluation.main(["--cases-dir", str(tmp_path), "--output", str(tmp_path / "results.json")]) == 1
    provider_factory.assert_not_called()
    assert not (tmp_path / "results.json").exists()


def test_missing_key_error_is_safe(
    tmp_path: Path, provider_factory: MagicMock, capsys: pytest.CaptureFixture[str],
) -> None:
    provider_factory.side_effect = MuseConfigurationError("PRIVATE-TEST-KEY")
    path = tmp_path / "results.json"
    assert run_evaluation.main(["--output", str(path)]) == 1
    assert "PRIVATE-TEST-KEY" not in capsys.readouterr().err
    assert not path.exists()


def test_invalid_pricing_prevents_provider_call(
    tmp_path: Path, provider_factory: MagicMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_INPUT_PRICE_PER_MILLION", "2")
    assert run_evaluation.main(["--output", str(tmp_path / "results.json")]) == 1
    provider_factory.assert_not_called()


def test_single_case_filter_runs_only_requested_case(tmp_path: Path, provider_factory: MagicMock) -> None:
    output = tmp_path / "single.json"
    assert run_evaluation.main(["--case", "EVAL-008", "--output", str(output)]) == 0
    report = EvaluationReport.model_validate_json(output.read_text())
    assert [case.case_id for case in report.cases] == ["EVAL-008"]
    provider = provider_factory.return_value.__enter__.return_value
    assert provider.chat_completion.call_count == 1
    assert provider.structured_completion.call_count == 1
    messages = provider.chat_completion.call_args.args[0]
    initial = json.loads(messages[1]["content"].split("\n", 1)[1])
    assert initial["case_id"] == "EVAL-008"
    assert set(initial) == {"case_id", "panel_id", "initial_snapshot"}
    assert "hidden_ground_truth" not in str(provider.mock_calls)
    assert "expected_relevant_evidence" not in str(provider.mock_calls)


def test_targeted_reports_preserve_full_report(
    tmp_path: Path, provider_factory: MagicMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    full_report = tmp_path / "results.json"
    full_report.write_text("original live report")
    monkeypatch.setattr(run_evaluation, "DEFAULT_REPORT_PATH", full_report)
    assert run_evaluation.main(["--case", "EVAL-008", "--case", "EVAL-004", "--case", "EVAL-008"]) == 0
    assert full_report.read_text() == "original live report"
    files = list((tmp_path / "reports").glob("*.json"))
    assert len(files) == 1
    report = EvaluationReport.model_validate_json(files[0].read_text())
    assert [case.case_id for case in report.cases] == ["EVAL-004", "EVAL-008"]
    assert provider_factory.return_value.__enter__.return_value.chat_completion.call_count == 2


def test_unknown_case_filter_never_constructs_provider(tmp_path: Path, provider_factory: MagicMock) -> None:
    assert run_evaluation.main(["--case", "UNAVAILABLE", "--output", str(tmp_path / "results.json")]) == 1
    provider_factory.assert_not_called()


def test_cli_retries_transient_provider_failure_once(
    tmp_path: Path, provider_factory: MagicMock, capsys: pytest.CaptureFixture[str],
) -> None:
    provider = provider_factory.return_value.__enter__.return_value
    success = provider.chat_completion.return_value
    provider.chat_completion.side_effect = [MuseAPIError("PRIVATE-TRANSIENT-CREDENTIAL"), success]
    path = tmp_path / "retried.json"
    assert run_evaluation.main(["--case", "EVAL-008", "--output", str(path)]) == 0
    report = EvaluationReport.model_validate_json(path.read_text())
    assert report.cases[0].attempt_count == 2
    assert report.cases[0].error is None
    assert report.cases[0].attempt_errors[0].code == "PROVIDER_FAILED"
    assert provider.chat_completion.call_count == 2
    assert report.metrics.usage_complete is False
    assert report.metrics.cost_is_partial is True
    output = capsys.readouterr()
    assert output.out.count("retrying case once (attempt 2/2)") == 1
    assert "PRIVATE-TRANSIENT-CREDENTIAL" not in output.out + output.err + path.read_text()
