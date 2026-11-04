"""All image-understanding requests are mocked; real schemas/runtime are exercised."""

import json
from unittest.mock import MagicMock

import pytest
from openai.types.chat import ParsedChatCompletion
from PIL import Image
from pydantic import ValidationError

from backend.evidence.converters import visual_observation_to_evidence
from backend.tools.models import VisualConditionRequest
from backend.tools.runtime import ScenarioToolRuntime
from backend.vision import assets
from backend.vision.errors import SamImageError
from backend.vision.models import ComponentBox, SegmentationResult
from backend.vision.observation_errors import (
    VisualObservationConfigurationError, VisualObservationProviderError, VisualObservationSchemaError,
)
from backend.vision.observation_models import VisualObservation, VisualObservationResult
from backend.vision.observation_provider import MuseVisualProvider


def observation(quality="SUFFICIENT", component="electrical terminal") -> VisualObservationResult:
    return VisualObservationResult(component=component, image_quality=quality, observations=[] if quality == "INSUFFICIENT" else [
        VisualObservation(feature="localized discoloration", description="Dark discoloration is visible around one terminal lug.", confidence=0.85),
    ])


def completion(result=None, *, parsed=True, finish="stop", refusal=None):
    result = observation() if result is None else result
    return ParsedChatCompletion[VisualObservationResult].model_validate({
        "id": "vision-mock", "object": "chat.completion", "created": 1, "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant",
            "content": result.model_dump_json(), "parsed": result if parsed else None, "refusal": refusal}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                  "completion_tokens_details": {"reasoning_tokens": 5}},
    })


@pytest.fixture
def image(tmp_path, monkeypatch):
    path = tmp_path / "demo/assets/terminal.png"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (100, 100)).save(path)
    monkeypatch.setattr(assets, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(assets, "ASSET_ROOT", path.parent)
    return path


def runtime_for(case, provider, *, reference="demo/assets/terminal.png", sam_provider=None):
    data = case.to_scenario_data().model_copy(update={"optional_image": reference})
    return ScenarioToolRuntime(data, reliability=0.8, visual_provider=provider, sam_provider=sam_provider)


def test_successful_observation_request_format_and_usage(image):
    client = MagicMock()
    client.chat.completions.parse.return_value = completion()
    provider = MuseVisualProvider(client=client)
    assert provider.observe(image, "Electrical  Terminal") == observation()
    call = client.chat.completions.parse.call_args.kwargs
    assert call["model"] == "muse-spark-1.3"
    assert call["response_format"] is VisualObservationResult and "tools" not in call
    assert call["messages"][0]["role"] == "developer"
    user = call["messages"][1]
    assert user["role"] == "user"
    assert user["content"][0]["type"] == "text"
    assert user["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert provider.usage.request_count == 1 and provider.usage.input_tokens == 100
    assert provider.usage.output_tokens == 20 and provider.usage.reasoning_tokens == 5
    assert provider.usage.total_tokens == 120
    client.close.assert_not_called()


@pytest.mark.parametrize("quality", ["LIMITED", "INSUFFICIENT"])
def test_restricted_image_quality_is_preserved(image, quality):
    client = MagicMock()
    client.chat.completions.parse.return_value = completion(observation(quality))
    result = MuseVisualProvider(client=client).observe(image, "electrical terminal")
    assert result.image_quality == quality
    if quality == "INSUFFICIENT":
        assert result.observations == []


def test_environment_config_fixed_model_and_owned_client(image, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "TEST-VISUAL-SECRET")
    monkeypatch.setenv("META_MODEL", "another-model")
    client = MagicMock()
    client.chat.completions.parse.return_value = completion()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr("backend.vision.observation_provider.OpenAI", factory)
    MuseVisualProvider().observe(image, "electrical terminal")
    assert factory.call_args.kwargs["base_url"] == "https://api.meta.ai/v1"
    assert factory.call_args.kwargs["api_key"] == "TEST-VISUAL-SECRET"
    assert client.chat.completions.parse.call_args.kwargs["model"] == "muse-spark-1.3"
    client.close.assert_called_once()


def test_missing_key_is_sanitized(image, monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(VisualObservationConfigurationError, match="META_API_KEY"):
        MuseVisualProvider().observe(image, "electrical terminal")


def test_missing_or_invalid_image_prevents_request(tmp_path):
    client = MagicMock()
    provider = MuseVisualProvider(client=client)
    for path in [tmp_path / "missing.jpg", tmp_path / "bad.jpg"]:
        if path.name == "bad.jpg":
            path.write_text("not raster data")
        with pytest.raises(SamImageError):
            provider.observe(path, "electrical terminal")
    client.chat.completions.parse.assert_not_called()


def test_provider_failure_redaction(image):
    client = MagicMock()
    client.chat.completions.parse.side_effect = RuntimeError("TEST-VISUAL-SECRET")
    provider = MuseVisualProvider(client=client)
    with pytest.raises(VisualObservationProviderError) as error:
        provider.observe(image, "electrical terminal")
    assert "SECRET" not in str(error.value) and error.value.__suppress_context__
    assert provider.usage.request_count == 1 and provider.usage.requests_with_usage == 0


@pytest.mark.parametrize("kwargs", [{"parsed": False}, {"finish": "length"}, {"refusal": "Refused"}])
def test_structured_response_required(image, kwargs):
    client = MagicMock()
    client.chat.completions.parse.return_value = completion(**kwargs)
    with pytest.raises(VisualObservationSchemaError):
        MuseVisualProvider(client=client).observe(image, "electrical terminal")


@pytest.mark.parametrize("text", [
    "loose connection", "connection fault", "overheating", "electrical failure", "unsafe", "dangerous",
    "No overheating is present", "LOOSE TERMINAL", "over-heated material", "over\u200bheating",
    "Discoloration caused by current", "Dark residue indicates a fault", "Repair the terminal",
])
@pytest.mark.parametrize("field", ["feature", "description"])
def test_forbidden_language_rejected(text, field):
    values = {"feature": "discoloration", "description": "Dark material is visible.", "confidence": 0.8}
    values[field] = text
    with pytest.raises(ValidationError):
        VisualObservation(**values)


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan"), True, "0.8"])
def test_observation_confidence_validation(value):
    with pytest.raises(ValidationError):
        VisualObservation(feature="residue", description="Residue is visible.", confidence=value)


def test_invalid_quality_extra_fields_and_insufficient_findings_rejected():
    data = observation().model_dump()
    for update in [{"image_quality": "GOOD"}, {"diagnosis": "unknown"}, {"image_quality": "INSUFFICIENT"}]:
        with pytest.raises(ValidationError):
            VisualObservationResult.model_validate({**data, **update})


def test_injected_unvalidated_diagnosis_is_rejected(image):
    bad = observation().model_copy(update={"observations": [VisualObservation.model_construct(
        feature="condition", description="Loose connection caused overheating.", confidence=0.8)]})
    client = MagicMock()
    # A constructed SDK response bypasses SDK validation; provider must still revalidate.
    response = completion()
    response.choices[0].message.parsed = bad
    client.chat.completions.parse.return_value = response
    with pytest.raises(VisualObservationSchemaError):
        MuseVisualProvider(client=client).observe(image, "electrical terminal")


def test_evidence_dedup_and_sam_link(image, connection_overheating_case):
    provider = MagicMock()
    provider.observe.return_value = observation()
    sam = MagicMock()
    sam.segment.return_value = SegmentationResult(concept="electrical terminal", objects_found=1,
        image_width=100, image_height=100,
        boxes=[ComponentBox(object_id="0", left=10, top=10, right=40, bottom=40)], masks=[])
    runtime = runtime_for(connection_overheating_case, provider, sam_provider=sam)
    runtime.inspect_component_image("GP-021", "electrical terminal")
    result = runtime.inspect_visual_condition("GP-021", "Electrical  Terminal")
    repeated = runtime.inspect_visual_condition("GP-021", "electrical terminal")
    assert result.evidence_ids_added == ["EV-002"]
    assert repeated.evidence_ids == ["EV-002"] and repeated.evidence_ids_added == []
    provider.observe.assert_called_once_with(image, "electrical terminal")
    record = runtime.evidence_ledger.get("EV-002")
    assert record.source == "VISION" and record.type == "VISUAL_COMPONENT_OBSERVATION"
    assert record.metadata["vision_model"] == "muse-spark-1.3"
    assert record.metadata["sam_evidence_ids"] == ["EV-001"]
    assert record.metadata["observations"][0]["confidence"] == 0.85
    assert record.metadata["image_identifier"] == "component-image.png"
    assert record.summary == observation().observations[0].description
    assert "hidden_ground_truth" not in result.model_dump_json()
    assert "expected_relevant_evidence" not in record.model_dump_json()
    result.observations.clear()
    assert runtime.inspect_visual_condition("GP-021", "electrical terminal").observations


def test_observation_can_precede_sam_and_other_components_are_distinct(image, connection_overheating_case):
    provider = MagicMock()
    provider.observe.side_effect = lambda path, component: observation(component=component)
    runtime = runtime_for(connection_overheating_case, provider)
    runtime.inspect_visual_condition("GP-021", "electrical terminal")
    runtime.inspect_visual_condition("GP-021", "circuit breaker")
    records = runtime.evidence_ledger.list_all()
    assert [r.id for r in records] == ["EV-001", "EV-002"]
    assert all(r.metadata["sam_evidence_ids"] == [] for r in records)


def test_insufficient_quality_becomes_quality_evidence(image, connection_overheating_case):
    provider = MagicMock()
    provider.observe.return_value = observation("INSUFFICIENT")
    runtime = runtime_for(connection_overheating_case, provider)
    result = runtime.inspect_visual_condition("GP-021", "electrical terminal")
    assert result.status == "completed" and result.image_quality == "INSUFFICIENT"
    record = runtime.evidence_ledger.get("EV-001")
    assert record.metadata["observations"] == [] and record.value is None
    runtime.inspect_visual_condition("GP-021", "electrical terminal")
    provider.observe.assert_called_once()


@pytest.mark.parametrize("reference,code", [(None, "NO_SCENARIO_IMAGE"), ("demo/assets/missing.png", "IMAGE_UNAVAILABLE"),
    ("../secret.png", "IMAGE_PATH_REJECTED"), ("/etc/passwd", "IMAGE_PATH_REJECTED")])
def test_missing_and_unsafe_images(image, connection_overheating_case, reference, code):
    provider = MagicMock()
    runtime = runtime_for(connection_overheating_case, provider, reference=reference)
    result = runtime.inspect_visual_condition("GP-021", "electrical terminal")
    assert result.status == "unavailable" and result.error_code == code
    provider.observe.assert_not_called()
    assert runtime.evidence_ledger.list_all() == []


def test_wrong_panel_and_arbitrary_path_argument_rejected(image, connection_overheating_case):
    provider = MagicMock()
    runtime = runtime_for(connection_overheating_case, provider)
    with pytest.raises(ValueError):
        runtime.inspect_visual_condition("GP-OTHER", "electrical terminal")
    with pytest.raises(ValidationError):
        VisualConditionRequest(panel_id="GP-021", component="electrical terminal", path=str(image))
    provider.observe.assert_not_called()


def test_runtime_failure_is_redacted_and_does_not_consume_id(image, connection_overheating_case):
    provider = MagicMock()
    provider.observe.side_effect = VisualObservationProviderError("TEST-VISUAL-SECRET")
    runtime = runtime_for(connection_overheating_case, provider)
    result = runtime.inspect_visual_condition("GP-021", "electrical terminal")
    assert result.status == "error" and result.error_code == "VISION_PROVIDER_FAILED"
    assert "SECRET" not in result.model_dump_json() and runtime.evidence_ledger.export() == []
    provider.observe.side_effect = None
    provider.observe.return_value = observation()
    assert runtime.inspect_visual_condition("GP-021", "electrical terminal").evidence_ids_added == ["EV-001"]


def test_converter_rejects_bypassed_diagnostic_claims(connection_overheating_case):
    bad = observation().model_copy(update={"observations": [VisualObservation.model_construct(
        feature="condition", description="Overheating", confidence=0.8)]})
    with pytest.raises(ValidationError):
        visual_observation_to_evidence(bad, image_identifier="component-image.png", evidence_id="EV-001",
            timestamp=connection_overheating_case.initial_snapshot.timestamp, reliability=0.8, sam_evidence_ids=[])


def test_manual_check_safe_structured_output(image, monkeypatch, capsys):
    from scripts.check_visual_api import main
    fake = MagicMock()
    fake.observe.return_value = observation()
    monkeypatch.setattr("scripts.check_visual_api.MuseVisualProvider", lambda: fake)
    assert main([str(image), "electrical terminal"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"component", "observations", "image_quality"}
    fake.observe.side_effect = VisualObservationProviderError("TEST-VISUAL-SECRET")
    assert main([str(image), "electrical terminal"]) == 1
    assert "SECRET" not in capsys.readouterr().out
