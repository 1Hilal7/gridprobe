"""Public API contracts using the real runtime/orchestrator and mocked Muse."""

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from openai.types.chat import ChatCompletion, ParsedChatCompletion

from backend.agent.contracts import DiagnosisResult
from backend.agent.errors import MissingMetaAPIKeyError, MuseAPIError, MuseResponseParsingError
from backend.api import service
from backend.api.main import app


def completion(*, content: str | None = None, calls: list[dict] | None = None) -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "test-completion", "object": "chat.completion", "created": 1, "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if calls else "stop", "message": {
            "role": "assistant", "content": content, "tool_calls": calls,
        }}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                  "completion_tokens_details": {"reasoning_tokens": 20}},
    })


@pytest.fixture(autouse=True)
def provider_factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    for variable in ("META_INPUT_PRICE_PER_MILLION", "META_OUTPUT_PRICE_PER_MILLION", "META_PRICE_CURRENCY"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("META_API_KEY", "PRIVATE-API-TEST-KEY")
    factory = MagicMock()
    provider = factory.return_value.__enter__.return_value
    provider.config.model = "muse-spark-1.3"

    def chat(messages: list, *, tools: list) -> ChatCompletion:
        if len(messages) == 2:
            initial = json.loads(messages[1]["content"].split("\n", 1)[1])
            return completion(content="PRIVATE_REASONING_TEST_MARKER", calls=[{
                "id": "call-phase", "type": "function", "function": {
                    "name": "calculate_phase_imbalance", "arguments": json.dumps({"panel_id": initial["panel_id"]}),
                },
            }])
        return completion(content="PRIVATE_REASONING_TEST_MARKER")

    def finalize(messages: list, *, response_format: type) -> ParsedChatCompletion[DiagnosisResult]:
        assert response_format is DiagnosisResult
        ledger = json.loads(messages[-1]["content"])["evidence_ledger"]
        diagnosis = DiagnosisResult(
            status="NEEDS_MORE_EVIDENCE", likely_fault="unknown", risk_level="UNKNOWN", confidence=0.4,
            evidence_ids=[record["id"] for record in ledger], reasoning_summary="Numerical observations were collected.",
            recommended_inspection="Additional inspection by qualified maintenance personnel.",
            missing_evidence=["Additional component observations"],
        )
        data = completion(content=diagnosis.model_dump_json()).model_dump()
        data["choices"][0]["message"]["parsed"] = diagnosis.model_dump()
        return ParsedChatCompletion[DiagnosisResult].model_validate(data)

    provider.chat_completion.side_effect = chat
    provider.structured_completion.side_effect = finalize
    monkeypatch.setattr(service, "MuseProvider", factory)
    return factory


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_scenario_listing_is_public_and_contains_four_cases(client: TestClient, provider_factory: MagicMock) -> None:
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    cases = response.json()
    assert [case["case_id"] for case in cases] == ["CASE-001", "CASE-002", "CASE-003", "CASE-004"]
    assert [case["panel_id"] for case in cases] == ["GP-021", "GP-017", "GP-033", "GP-044"]
    for case in cases:
        assert set(case) == {"case_id", "panel_id", "initial_snapshot", "image_available"}
        assert isinstance(case["image_available"], bool)
    assert "hidden_ground_truth" not in response.text
    assert "expected_relevant_evidence" not in response.text
    assert "optional_image" not in response.text
    provider_factory.assert_not_called()


def test_visual_investigation_serialization(client, provider_factory, monkeypatch, tmp_path) -> None:
    from PIL import Image
    from backend.vision import assets
    from backend.vision.models import ComponentBox, SegmentationResult

    path = tmp_path / "demo/assets/case_001_terminal.jpg"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (100, 100)).save(path)
    monkeypatch.setattr(assets, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(assets, "ASSET_ROOT", path.parent)
    sam = MagicMock()
    sam.segment.return_value = SegmentationResult(concept="electrical terminal", objects_found=1,
        image_width=100, image_height=100,
        boxes=[ComponentBox(object_id="0", left=10, top=10, right=40, bottom=40)], masks=[])
    monkeypatch.setattr("backend.tools.runtime.SamProvider", lambda: sam)
    provider = provider_factory.return_value.__enter__.return_value
    provider.chat_completion.side_effect = [completion(calls=[{
        "id": "visual", "type": "function", "function": {
            "name": "inspect_component_image", "arguments": json.dumps({"panel_id": "GP-021", "concept": "electrical terminal"}),
        },
    }]), completion(content="Done")]
    response = client.post("/api/investigations", json={"case_id": "CASE-001"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case"]["image_available"] is True
    assert body["evidence"][0]["source"] == "VISION"
    assert body["evidence"][0]["metadata"]["boxes"][0]["right"] == 40
    assert body["trace"][2]["tool_result"]["mask_count"] == 0
    assert "hidden_ground_truth" not in response.text and "expected_relevant_evidence" not in response.text
    assert "PRIVATE-API-TEST-KEY" not in response.text
    assert "optional_image" not in response.text
    assert client.get("/api/scenarios/CASE-001/image").status_code == 200


def test_visual_condition_public_output(client, provider_factory, monkeypatch, tmp_path) -> None:
    from backend.vision.observation_models import VisualObservation, VisualObservationResult
    monkeypatch.setattr("backend.tools.runtime.resolve_scenario_image", lambda reference: tmp_path / "terminal.jpg")
    vision = MagicMock()
    vision.observe.return_value = VisualObservationResult(component="electrical terminal", image_quality="LIMITED",
        observations=[VisualObservation(feature="dark material", description="Dark material is visible on one lug.", confidence=0.7)])
    monkeypatch.setattr("backend.tools.runtime.MuseVisualProvider", lambda: vision)
    provider = provider_factory.return_value.__enter__.return_value
    provider.chat_completion.side_effect = [completion(calls=[{
        "id": "condition", "type": "function", "function": {
            "name": "inspect_visual_condition", "arguments": json.dumps({"panel_id": "GP-021", "component": "electrical terminal"}),
        },
    }]), completion(content="Done")]
    response = client.post("/api/investigations", json={"case_id": "CASE-001"})
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"][0]
    assert evidence["metadata"]["vision_model"] == "muse-spark-1.3"
    assert evidence["metadata"]["image_quality"] == "LIMITED"
    assert "hidden_ground_truth" not in response.text and "expected_relevant_evidence" not in response.text
    assert "PRIVATE-API-TEST-KEY" not in response.text


@pytest.mark.parametrize("case_id", ["CASE-001", "CASE-002", "CASE-003", "CASE-004"])
def test_mocked_investigation_uses_real_agent_and_serializes_public_result(
    client: TestClient, provider_factory: MagicMock, case_id: str,
) -> None:
    response = client.post("/api/investigations", json={"case_id": case_id})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case"]["case_id"] == case_id
    assert len(body["case"]["history"]) == 6
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["id"] == "EV-001"
    assert body["evidence"][0]["type"] == "PHASE_IMBALANCE"
    assert body["diagnosis"]["evidence_ids"] == ["EV-001"]
    assert body["diagnosis"]["status"] == "NEEDS_MORE_EVIDENCE"
    assert body["usage"]["request_count"] == 3
    assert body["usage"]["input_tokens"] == 300
    assert body["usage"]["output_tokens"] == 150
    assert body["usage"]["reasoning_tokens"] == 60
    assert body["estimated_cost_usd"] == pytest.approx((300 * 1.25 + 150 * 4.25) / 1_000_000)
    assert body["cost_is_partial"] is False
    assert [step["step_number"] for step in body["trace"]] == [1, 2, 3, 4, 5]
    assert body["trace"][2]["evidence_ids_added"] == ["EV-001"]
    for forbidden in ("hidden_ground_truth", "expected_relevant_evidence", "PRIVATE-API-TEST-KEY",
                      "PRIVATE_REASONING_TEST_MARKER", "assistant_content", "base_url", "optional_image"):
        assert forbidden not in response.text
    if case_id == "CASE-002":
        assert body["evidence"][0]["value"] == pytest.approx(28.1, abs=0.01)
    provider = provider_factory.return_value.__enter__.return_value
    initial = json.loads(provider.chat_completion.call_args_list[0].args[0][1]["content"].split("\n", 1)[1])
    assert set(initial) == {"case_id", "panel_id", "initial_snapshot"}
    assert "hidden_ground_truth" not in str(provider.mock_calls)


@pytest.mark.parametrize("case_id", ["CASE-999", "EVAL-001", "../.env"])
def test_unknown_scenario_returns_404_before_provider(client: TestClient, provider_factory: MagicMock, case_id: str) -> None:
    response = client.post("/api/investigations", json={"case_id": case_id})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"
    provider_factory.assert_not_called()


def test_missing_key_configuration_is_safe(client: TestClient, provider_factory: MagicMock) -> None:
    provider_factory.side_effect = MissingMetaAPIKeyError("PRIVATE-API-TEST-KEY")
    response = client.post("/api/investigations", json={"case_id": "CASE-001"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_CONFIGURED"
    assert "PRIVATE-API-TEST-KEY" not in response.text


def test_provider_failure_is_sanitized(client: TestClient, provider_factory: MagicMock) -> None:
    provider_factory.return_value.__enter__.return_value.chat_completion.side_effect = MuseAPIError("PRIVATE-API-TEST-KEY")
    response = client.post("/api/investigations", json={"case_id": "CASE-002"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert response.json()["error"]["retryable"] is True
    assert "PRIVATE-API-TEST-KEY" not in response.text


def test_invalid_diagnosis_is_sanitized(client: TestClient, provider_factory: MagicMock) -> None:
    provider_factory.return_value.__enter__.return_value.structured_completion.side_effect = MuseResponseParsingError("PRIVATE-API-TEST-KEY")
    response = client.post("/api/investigations", json={"case_id": "CASE-002"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "INVALID_DIAGNOSIS"
    assert "PRIVATE-API-TEST-KEY" not in response.text


def test_cost_override_and_no_reasoning_double_charge(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_INPUT_PRICE_PER_MILLION", "2")
    monkeypatch.setenv("META_OUTPUT_PRICE_PER_MILLION", "10")
    response = client.post("/api/investigations", json={"case_id": "CASE-002"})
    assert response.status_code == 200
    assert response.json()["estimated_cost_usd"] == pytest.approx(0.0021)


def test_non_usd_configuration_cannot_be_mislabeled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_PRICE_CURRENCY", "EUR")
    response = client.post("/api/investigations", json={"case_id": "CASE-001"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PRICING_NOT_CONFIGURED"


def test_missing_usage_does_not_fabricate_cost(client: TestClient, provider_factory: MagicMock) -> None:
    provider = provider_factory.return_value.__enter__.return_value
    chat = provider.chat_completion.side_effect
    finalize = provider.structured_completion.side_effect

    def chat_without_usage(*args, **kwargs):
        result = chat(*args, **kwargs)
        result.usage = None
        return result

    def final_without_usage(*args, **kwargs):
        result = finalize(*args, **kwargs)
        result.usage = None
        return result

    provider.chat_completion.side_effect = chat_without_usage
    provider.structured_completion.side_effect = final_without_usage
    response = client.post("/api/investigations", json={"case_id": "CASE-002"})
    assert response.status_code == 200
    assert response.json()["estimated_cost_usd"] is None
    assert response.json()["usage"]["total_tokens"] is None
    assert response.json()["cost_is_partial"] is True


def test_credential_echo_is_redacted_in_public_strings(client: TestClient, provider_factory: MagicMock) -> None:
    provider = provider_factory.return_value.__enter__.return_value
    finalize = provider.structured_completion.side_effect

    def finalize_with_echo(*args, **kwargs):
        result = finalize(*args, **kwargs)
        result.choices[0].message.parsed.reasoning_summary = "PRIVATE-API-TEST-KEY"
        return result

    provider.structured_completion.side_effect = finalize_with_echo
    response = client.post("/api/investigations", json={"case_id": "CASE-002"})
    assert response.status_code == 200
    assert "PRIVATE-API-TEST-KEY" not in response.text
    assert response.json()["diagnosis"]["reasoning_summary"] == "[REDACTED]"


def test_no_echo_of_private_request_fields(client: TestClient) -> None:
    response = client.post("/api/investigations", json={"case_id": "CASE-001", "hidden_ground_truth": "PRIVATE-API-TEST-KEY"})
    assert response.status_code == 422
    assert "PRIVATE-API-TEST-KEY" not in response.text
    assert "hidden_ground_truth" not in response.text


def test_local_cors_and_public_openapi(client: TestClient) -> None:
    response = client.options("/api/investigations", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    schema = client.get("/openapi.json").text
    assert "hidden_ground_truth" not in schema
    assert "expected_relevant_evidence" not in schema
