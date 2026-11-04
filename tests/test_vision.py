"""Offline SAM transport, parser, runtime, and public-boundary regression tests."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from backend.api.main import app
from backend.evidence.converters import visual_segmentation_to_evidence
from backend.scenarios.loader import load_scenario, DEFAULT_SCENARIO_DIRECTORY
from backend.tools.models import VisualRequest
from backend.tools.runtime import ScenarioToolRuntime
from backend.vision import assets
from backend.vision.assets import resolve_scenario_image
from backend.vision.errors import SamConfigurationError, SamImageError, SamParsingError, SamPathError, SamProviderError
from backend.vision.models import ComponentBox, MaskMetadata, SegmentationResult
from backend.vision.provider import SamProvider, read_image


@pytest.fixture
def image(tmp_path: Path) -> Path:
    path = tmp_path / "demo/assets/terminal.png"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (320, 334)).save(path)
    return path


@pytest.fixture
def asset_area(image: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(assets, "REPOSITORY_ROOT", image.parents[2])
    monkeypatch.setattr(assets, "ASSET_ROOT", image.parent)
    return image


def segmented(concept: str = "electrical terminal", *, empty: bool = False) -> SegmentationResult:
    return SegmentationResult(
        concept=concept, objects_found=0 if empty else 1, image_width=320, image_height=334,
        boxes=[] if empty else [ComponentBox(object_id="0", left=211, top=228, right=271, bottom=255)],
        masks=[] if empty else [MaskMetadata(object_id="0", encoding="lossless", width=60, height=27)],
    )


class FakeStream:
    def __init__(self, text: str, terminal: str = "response.completed") -> None:
        lane = {"item_id": "sam-test", "output_index": 0, "content_index": 0}
        self.events = [
            {"type": "response.output_text.delta", **lane, "delta": text[:20]},
            {"type": "response.output_text.delta", **lane, "delta": text[20:]},
            {"type": "response.content_part.done", **lane, "part": {"type": "output_text", "text": text}},
            {"type": terminal},
        ]
        self.closed = False

    def __aiter__(self):
        async def events():
            for event in self.events:
                yield event
        return events()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def aclose(self):
        self.closed = True


# Official parser README example, used only as a mocked wire response.
WIRE_OBJECT = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>\n"
)


def client_for(stream: FakeStream):
    return SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=stream)), close=AsyncMock())


def test_real_parser_with_mocked_successful_sdk_stream(image: Path) -> None:
    stream = FakeStream(WIRE_OBJECT)
    client = client_for(stream)
    result = SamProvider(client=client).segment(image, "electrical terminal")
    assert result.completed and result.objects_found == 1
    assert result.boxes[0].right == 271  # Official parser converts inclusive to half-open.
    assert result.masks[0].encoding == "lossless"
    assert result.masks[0].width == 60
    assert result.diagnostics == []
    call = client.responses.create.call_args.kwargs
    assert call["model"] == "sam-3.1" and call["stream"] is True
    assert call["input"][0]["content"][0] == {"type": "input_text", "text": "electrical terminal"}
    assert call["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert "raw_output" not in result.model_dump_json()
    assert stream.closed
    client.close.assert_not_awaited()  # Injected SDK clients remain caller-owned.


def test_completed_zero_match_is_valid(image: Path) -> None:
    result = SamProvider(client=client_for(FakeStream(""))).segment(image, "terminal")
    assert result.completed and result.objects_found == 0
    assert result.boxes == result.masks == []


@pytest.mark.parametrize("terminal", ["response.incomplete", "response.failed"])
def test_incomplete_and_failed_streams_rejected(image: Path, terminal: str) -> None:
    with pytest.raises((SamParsingError, SamProviderError)):
        SamProvider(client=client_for(FakeStream("", terminal))).segment(image, "terminal")


def test_malformed_segmentation_rejected(image: Path) -> None:
    with pytest.raises(SamParsingError):
        SamProvider(client=client_for(FakeStream("<0f>bad<|box;invalid|>\n"))).segment(image, "terminal")


def test_missing_image_before_sdk_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(SamImageError):
        SamProvider().segment(tmp_path / "missing.jpg", "terminal")


def test_invalid_image_not_sent(tmp_path: Path) -> None:
    path = tmp_path / "pretend.jpg"
    path.write_text("not an image")
    client = client_for(FakeStream(""))
    with pytest.raises(SamImageError):
        SamProvider(client=client).segment(path, "terminal")
    client.responses.create.assert_not_called()


def test_oversized_image_rejected(image: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.vision.provider.MAX_IMAGE_BYTES", 10)
    with pytest.raises(SamImageError):
        read_image(image)


def test_missing_key_is_clear(image: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(SamConfigurationError, match="META_API_KEY"):
        SamProvider().segment(image, "terminal")


def test_sdk_configuration_and_client_cleanup(image: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_API_KEY", "sam-test-secret")
    monkeypatch.setenv("META_MODEL", "muse-spark-1.3")
    client = client_for(FakeStream(""))
    factory = MagicMock(return_value=client)
    monkeypatch.setattr("backend.vision.provider.AsyncOpenAI", factory)
    SamProvider().segment(image, "terminal")
    assert factory.call_args.kwargs["base_url"] == "https://api.meta.ai/v1"
    assert factory.call_args.kwargs["api_key"] == "sam-test-secret"
    assert client.responses.create.call_args.kwargs["model"] == "sam-3.1"
    client.close.assert_awaited_once()


def test_provider_failure_redacted(image: Path) -> None:
    client = client_for(FakeStream(""))
    client.responses.create.side_effect = RuntimeError("PRIVATE-SAM-KEY raw provider body")
    with pytest.raises(SamProviderError) as caught:
        SamProvider(client=client).segment(image, "terminal")
    assert "PRIVATE" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("reference", ["../secret.jpg", "demo/assets/../secret.jpg", "/etc/passwd", "demo/scenarios/data.json", "demo\\assets\\terminal.png", "demo/assets/a\x00.png"])
def test_unsafe_paths_rejected(asset_area: Path, reference: str) -> None:
    with pytest.raises(SamPathError):
        resolve_scenario_image(reference)


def test_symlink_escape_rejected(asset_area: Path, tmp_path: Path) -> None:
    secret = tmp_path / "outside.jpg"
    secret.write_bytes(b"private")
    (asset_area.parent / "escape.jpg").symlink_to(secret)
    with pytest.raises(SamPathError):
        resolve_scenario_image("demo/assets/escape.jpg")


@pytest.mark.parametrize("concept", ["", "loose connection", "overheating", "ignore instructions", "terminal; read file", "terminal\nignore instructions", "a b c d e f g"])
def test_concept_guard(concept: str) -> None:
    with pytest.raises(ValidationError):
        VisualRequest(panel_id="GP-021", concept=concept)


def visual_runtime(case, provider, reference="demo/assets/terminal.png"):
    data = case.to_scenario_data().model_copy(update={"optional_image": reference})
    return ScenarioToolRuntime(data, reliability=0.8, sam_provider=provider)


def test_visual_evidence_dedup_sequential_ids_and_no_diagnosis(asset_area, connection_overheating_case) -> None:
    provider = MagicMock()
    provider.segment.side_effect = lambda path, concept: segmented(concept)
    runtime = visual_runtime(connection_overheating_case, provider)
    runtime.calculate_phase_imbalance("GP-021")
    result = runtime.inspect_component_image("GP-021", "Electrical   Terminal")
    repeat = runtime.inspect_component_image("GP-021", "electrical terminal")
    assert result.evidence_ids_added == ["EV-002"]
    assert repeat.evidence_ids == ["EV-002"] and repeat.evidence_ids_added == []
    provider.segment.assert_called_once_with(asset_area, "electrical terminal")
    runtime.inspect_component_image("GP-021", "circuit breaker")
    assert [r.id for r in runtime.evidence_ledger.list_all()] == ["EV-001", "EV-002", "EV-003"]
    record = runtime.evidence_ledger.get("EV-002")
    assert record.source == "VISION" and record.type == "VISUAL_COMPONENT_OBSERVATION"
    assert record.metadata["boxes"][0]["right"] == 271
    assert record.metadata["mask_count"] == 1 and record.metadata["sam_model"] == "sam-3.1"
    assert record.metadata["image_identifier"] == "component-image.png"
    serialized = record.model_dump_json().lower()
    for forbidden in ["dangerous", "faulty", "loose connection", "overheating", "hidden_ground_truth", "expected_relevant_evidence"]:
        assert forbidden not in serialized
    result.boxes.clear()
    assert runtime.inspect_component_image("GP-021", "electrical terminal").boxes


def test_zero_match_creates_evidence(asset_area, connection_overheating_case) -> None:
    provider = MagicMock()
    provider.segment.return_value = segmented(empty=True)
    runtime = visual_runtime(connection_overheating_case, provider)
    result = runtime.inspect_component_image("GP-021", "electrical terminal")
    assert result.status == "completed" and result.objects_found == 0 and result.mask_count == 0
    assert runtime.evidence_ledger.get("EV-001").value == 0


@pytest.mark.parametrize("reference,code", [("demo/assets/missing.jpg", "IMAGE_UNAVAILABLE"), ("../private.jpg", "IMAGE_PATH_REJECTED")])
def test_unavailable_runtime_does_not_call_sam(asset_area, connection_overheating_case, reference, code) -> None:
    provider = MagicMock()
    runtime = visual_runtime(connection_overheating_case, provider, reference)
    result = runtime.inspect_component_image("GP-021", "electrical terminal")
    assert result.status == "unavailable" and result.error_code == code
    provider.segment.assert_not_called()
    assert runtime.evidence_ledger.list_all() == []


def test_runtime_provider_failure_is_structured_and_redacted(asset_area, connection_overheating_case) -> None:
    provider = MagicMock()
    provider.segment.side_effect = SamProviderError("PRIVATE-SAM-KEY")
    runtime = visual_runtime(connection_overheating_case, provider)
    result = runtime.inspect_component_image("GP-021", "electrical terminal")
    assert result.status == "error" and result.error_code == "SAM_PROVIDER_FAILED"
    assert "PRIVATE" not in result.model_dump_json()
    provider.segment.side_effect = None
    provider.segment.return_value = segmented()
    assert runtime.inspect_component_image("GP-021", "electrical terminal").evidence_ids_added == ["EV-001"]


def test_wrong_panel_does_not_call_sam(asset_area, connection_overheating_case) -> None:
    provider = MagicMock()
    runtime = visual_runtime(connection_overheating_case, provider)
    with pytest.raises(ValueError):
        runtime.inspect_component_image("GP-OTHER", "electrical terminal")
    provider.segment.assert_not_called()


@pytest.mark.parametrize("filename", ["case_002_phase_imbalance.json", "case_003_overload.json", "case_004_normal_or_insufficient.json"])
def test_imageless_scenarios_continue_without_sam(filename: str) -> None:
    case = load_scenario(DEFAULT_SCENARIO_DIRECTORY / filename)
    provider = MagicMock()
    runtime = ScenarioToolRuntime(case.to_scenario_data(), reliability=1.0, sam_provider=provider)
    assert runtime.inspect_component_image(case.panel_id, "terminal").error_code == "NO_SCENARIO_IMAGE"
    assert runtime.calculate_phase_imbalance(case.panel_id).average_current > 0
    assert runtime.calculate_temperature_trend(case.panel_id, 60).duration_minutes == 60
    provider.segment.assert_not_called()


def test_converter_contains_only_geometry(connection_overheating_case) -> None:
    record = visual_segmentation_to_evidence(segmented(), image_identifier="component-image.png",
        evidence_id="EV-001", timestamp=connection_overheating_case.initial_snapshot.timestamp, reliability=0.8)
    assert record.value == 1 and record.unit == "objects"
    assert "payload" not in record.model_dump_json()


def test_safe_image_endpoint(asset_area, connection_overheating_case, monkeypatch) -> None:
    from backend.api import service
    data = connection_overheating_case.to_scenario_data().model_copy(update={"optional_image": "demo/assets/terminal.png"})
    monkeypatch.setattr(service, "_load_primary", lambda case_id: data)
    with TestClient(app) as client:
        response = client.get("/api/scenarios/CASE-001/image")
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.content == asset_area.read_bytes()
    assert response.headers["x-content-type-options"] == "nosniff"


def test_image_endpoint_missing_and_unknown() -> None:
    with TestClient(app) as client:
        assert client.get("/api/scenarios/CASE-004/image").status_code == 404
        assert client.get("/api/scenarios/EVAL-001/image").status_code == 404


def test_manual_check_output_and_missing_image(image, tmp_path, monkeypatch, capsys) -> None:
    from scripts.check_sam_api import main
    fake = MagicMock()
    fake.segment.return_value = segmented()
    monkeypatch.setattr("scripts.check_sam_api.SamProvider", lambda: fake)
    assert main([str(image), "electrical terminal"]) == 0
    assert json.loads(capsys.readouterr().out)["objects_found"] == 1
    fake.segment.side_effect = SamImageError("PRIVATE-SAM-KEY")
    assert main([str(tmp_path / "missing.jpg"), "terminal"]) == 1
    assert "PRIVATE" not in capsys.readouterr().out
