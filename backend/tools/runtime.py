"""Scenario-scoped, non-AI tool runtime with deterministic evidence IDs."""

from datetime import datetime, timezone

from pydantic import TypeAdapter
from backend.agent.models import ModelUsageSummary

from backend.evidence.converters import (
    maintenance_context_to_evidence, phase_imbalance_to_evidence,
    sensor_history_to_evidence, temperature_trend_to_evidence,
    visual_segmentation_to_evidence,
    visual_observation_to_evidence,
)
from backend.evidence.ledger import EvidenceLedger
from backend.scenarios.models import MaintenanceContext, ScenarioData, TelemetryHistoryPoint, TelemetrySnapshot
from backend.tools import electrical
from backend.tools.electrical import PhaseImbalanceResult, TemperatureTrendResult
from backend.tools.models import (
    HistoryRequest, InitialContext, PanelRequest, Reliability, Sensor,
    SensorHistoryPoint, SensorHistoryResult, TrendRequest, VisualRequest, VisualConditionRequest,
)
from backend.vision.assets import resolve_scenario_image
from backend.vision.errors import SamError, SamImageError, SamPathError
from backend.vision.models import SegmentationResult, VisualToolResult
from backend.vision.provider import SamProvider
from backend.vision.observation_errors import VisualObservationError
from backend.vision.observation_models import VisualConditionToolResult, VisualObservationResult
from backend.vision.observation_provider import MuseVisualProvider


class ScenarioToolRuntime:
    """One fixed scenario and one investigation-owned ledger.

    The input must be exactly ScenarioData, excluding subclasses that could
    carry evaluation annotations. A deep copy fixes the data for this runtime.
    Only initial_context() is intended as the initial model input.

    Successful evidence-producing requests are cached by tool, active panel,
    and normalized arguments. History uses (sensor, float minutes), trends use
    float minutes, and phase/maintenance each use one entry. Thus 60 and 60.0
    share a cache entry. Repeated requests return independent result copies
    without recalculation or new evidence. Different windows produce separate
    evidence, even when they contain the same points. Failures consume no IDs.
    IDs follow successful evidence-producing request order: EV-001, EV-002, ... .
    This synchronous runtime owns its ledger; callers may read it but should
    not insert evidence independently. A new runtime starts a new investigation.
    """

    def __init__(
        self, data: ScenarioData, *, reliability: float,
        evidence_ledger: EvidenceLedger | None = None,
        sam_provider: SamProvider | None = None,
        visual_provider: MuseVisualProvider | None = None,
    ) -> None:
        if type(data) is not ScenarioData:
            raise TypeError("Pass a plain ScenarioData projection to the tool runtime.")
        self._data = ScenarioData.model_validate(data.model_dump()).model_copy(deep=True)
        self._reliability = TypeAdapter(Reliability).validate_python(reliability)
        timestamps = [self._data.initial_snapshot.timestamp, *[point.timestamp for point in self._data.history]]
        aware = [timestamp.utcoffset() is not None for timestamp in timestamps]
        if any(aware) and not all(aware):
            raise ValueError("timestamps must be uniformly timezone-aware or naive")
        self._ledger = evidence_ledger if evidence_ledger is not None else EvidenceLedger()
        if self._ledger.list_all():
            raise ValueError("A new investigation requires an empty evidence ledger.")
        self._next_evidence_number = 1
        self._phase_result: PhaseImbalanceResult | None = None
        self._trend_results: dict[float, TemperatureTrendResult] = {}
        self._history_results: dict[tuple[Sensor, float], SensorHistoryResult] = {}
        self._maintenance_context: MaintenanceContext | None = None
        self._sam_provider = sam_provider
        self._visual_results: dict[str, VisualToolResult] = {}
        self._visual_provider = visual_provider
        self._condition_results: dict[str, VisualConditionToolResult] = {}

    @property
    def visual_usage(self) -> ModelUsageSummary:
        usage = self._visual_provider.usage if self._visual_provider is not None else None
        return usage.model_copy(deep=True) if isinstance(usage, ModelUsageSummary) else ModelUsageSummary()

    @property
    def evidence_ledger(self) -> EvidenceLedger:
        """The investigation-owned evidence ledger, available for inspection."""
        return self._ledger

    def initial_context(self) -> InitialContext:
        """Expose only identifiers and the initial/current snapshot."""
        return InitialContext(
            case_id=self._data.case_id,
            panel_id=self._data.panel_id,
            initial_snapshot=self._data.initial_snapshot.model_copy(deep=True),
        )

    def _validate_panel(self, panel_id: str) -> None:
        request = PanelRequest(panel_id=panel_id)
        if request.panel_id != self._data.panel_id:
            raise ValueError("panel_id does not match the active scenario")

    @staticmethod
    def _instant(timestamp: datetime) -> datetime:
        return timestamp.astimezone(timezone.utc) if timestamp.utcoffset() is not None else timestamp

    def _history_window(self, minutes: float) -> list[TelemetryHistoryPoint]:
        current = self._instant(self._data.initial_snapshot.timestamp)
        # Compare ages instead of subtracting a potentially overflowing timedelta.
        points = [
            point for point in self._data.history
            if 0 <= (current - self._instant(point.timestamp)).total_seconds() / 60 <= minutes
        ]
        return sorted(points, key=lambda point: self._instant(point.timestamp))

    def get_current_snapshot(self, panel_id: str) -> TelemetrySnapshot:
        self._validate_panel(panel_id)
        return self._data.initial_snapshot.model_copy(deep=True)

    def get_sensor_history(self, panel_id: str, sensor: Sensor, minutes: float) -> SensorHistoryResult:
        self._validate_panel(panel_id)
        request = HistoryRequest(panel_id=panel_id, sensor=sensor, minutes=minutes)
        key = (request.sensor, request.minutes)
        if key not in self._history_results:
            result = SensorHistoryResult(
                panel_id=panel_id, sensor=request.sensor, minutes=request.minutes,
                points=[
                    SensorHistoryPoint(timestamp=point.timestamp, value=getattr(point, request.sensor))
                    for point in self._history_window(request.minutes)
                ],
            )
            record = sensor_history_to_evidence(
                result, evidence_id=f"EV-{self._next_evidence_number:03d}",
                timestamp=self._data.initial_snapshot.timestamp, reliability=self._reliability,
            )
            self._ledger.add(record)
            self._next_evidence_number += 1
            self._history_results[key] = result.model_copy(deep=True)
        return self._history_results[key].model_copy(deep=True)

    def calculate_phase_imbalance(self, panel_id: str) -> PhaseImbalanceResult:
        self._validate_panel(panel_id)
        if self._phase_result is None:
            snapshot = self._data.initial_snapshot
            result = electrical.calculate_phase_imbalance(
                snapshot.current_a, snapshot.current_b, snapshot.current_c
            )
            record = phase_imbalance_to_evidence(
                result, evidence_id=f"EV-{self._next_evidence_number:03d}",
                timestamp=snapshot.timestamp, reliability=self._reliability,
            )
            record = record.model_copy(update={"metadata": {**record.metadata, "panel_id": panel_id}})
            self._ledger.add(record)
            self._next_evidence_number += 1
            self._phase_result = result.model_copy(deep=True)
        return self._phase_result.model_copy(deep=True)

    def calculate_temperature_trend(self, panel_id: str, minutes: float) -> TemperatureTrendResult:
        self._validate_panel(panel_id)
        request = TrendRequest(panel_id=panel_id, minutes=minutes)
        if request.minutes not in self._trend_results:
            snapshot = self._data.initial_snapshot
            result = electrical.calculate_temperature_trend(self._history_window(request.minutes), snapshot)
            record = temperature_trend_to_evidence(
                result, evidence_id=f"EV-{self._next_evidence_number:03d}",
                timestamp=snapshot.timestamp, reliability=self._reliability,
            )
            record = record.model_copy(update={"metadata": {
                **record.metadata, "panel_id": panel_id, "requested_minutes": request.minutes,
            }})
            self._ledger.add(record)
            self._next_evidence_number += 1
            self._trend_results[request.minutes] = result.model_copy(deep=True)
        return self._trend_results[request.minutes].model_copy(deep=True)

    def get_maintenance_context(self, panel_id: str) -> MaintenanceContext:
        self._validate_panel(panel_id)
        if self._maintenance_context is None:
            result = self._data.maintenance_context.model_copy(deep=True)
            record = maintenance_context_to_evidence(
                result, evidence_id=f"EV-{self._next_evidence_number:03d}",
                timestamp=self._data.initial_snapshot.timestamp, reliability=self._reliability,
            )
            record = record.model_copy(update={"metadata": {**record.metadata, "panel_id": panel_id}})
            self._ledger.add(record)
            self._next_evidence_number += 1
            self._maintenance_context = result.model_copy(deep=True)
        return self._maintenance_context.model_copy(deep=True)

    def inspect_component_image(self, panel_id: str, concept: str) -> VisualToolResult:
        self._validate_panel(panel_id)
        request = VisualRequest(panel_id=panel_id, concept=concept)
        if request.concept in self._visual_results:
            # Existing evidence remains referenceable, but no new IDs were added.
            return self._visual_results[request.concept].model_copy(deep=True, update={"evidence_ids_added": []})
        if self._data.optional_image is None:
            return VisualToolResult(status="unavailable", concept=request.concept,
                                    error_code="NO_SCENARIO_IMAGE", message="No image is supplied for this panel.")
        try:
            path = resolve_scenario_image(self._data.optional_image)
            provider = self._sam_provider if self._sam_provider is not None else SamProvider()
            result = provider.segment(path, request.concept)
            result = SegmentationResult.model_validate(result.model_dump())
            if result.concept != request.concept:
                raise ValueError("Segmentation concept mismatch")
        except SamError as error:
            return VisualToolResult(
                status="unavailable" if isinstance(error, (SamImageError, SamPathError)) else "error",
                concept=request.concept, error_code=error.code,
                message="Visual inspection is unavailable; use other observations or request additional evidence.",
            )
        except Exception:
            return VisualToolResult(status="error", concept=request.concept, error_code="SAM_FAILED",
                                    message="Visual inspection could not be completed.")
        evidence_id = f"EV-{self._next_evidence_number:03d}"
        # The identifier must not carry scenario labels or filesystem details.
        suffix = path.suffix.lower()
        identifier = "component-image" + (suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else "")
        record = visual_segmentation_to_evidence(
            result, image_identifier=identifier, evidence_id=evidence_id,
            timestamp=self._data.initial_snapshot.timestamp, reliability=self._reliability,
        )
        self._ledger.add(record)
        self._next_evidence_number += 1
        response = VisualToolResult(
            status="completed", concept=result.concept, objects_found=result.objects_found,
            boxes=result.boxes, mask_count=len(result.masks), image_width=result.image_width,
            image_height=result.image_height, image_identifier=identifier,
            evidence_ids=[evidence_id], evidence_ids_added=[evidence_id],
        )
        self._visual_results[request.concept] = response.model_copy(deep=True)
        return response

    def inspect_visual_condition(self, panel_id: str, component: str) -> VisualConditionToolResult:
        self._validate_panel(panel_id)
        request = VisualConditionRequest(panel_id=panel_id, component=component)
        if request.component in self._condition_results:
            return self._condition_results[request.component].model_copy(deep=True, update={"evidence_ids_added": []})
        if self._data.optional_image is None:
            return VisualConditionToolResult(status="unavailable", component=request.component,
                error_code="NO_SCENARIO_IMAGE", message="No image is supplied for this panel.")
        try:
            path = resolve_scenario_image(self._data.optional_image)
            if self._visual_provider is None:
                self._visual_provider = MuseVisualProvider()
            result = self._visual_provider.observe(path, request.component)
            result = VisualObservationResult.model_validate(result.model_dump())
            if result.component != request.component:
                raise ValueError("Visual component mismatch")
        except (SamError, VisualObservationError) as error:
            return VisualConditionToolResult(
                status="unavailable" if isinstance(error, (SamImageError, SamPathError)) else "error",
                component=request.component, error_code=error.code,
                message="Visual condition observations are unavailable; request additional evidence if needed.",
            )
        except Exception:
            return VisualConditionToolResult(status="error", component=request.component,
                error_code="VISION_RESPONSE_INVALID", message="Visual condition observations could not be validated.")
        sam = self._visual_results.get(request.component)
        suffix = path.suffix.lower()
        identifier = "component-image" + (suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else "")
        evidence_id = f"EV-{self._next_evidence_number:03d}"
        record = visual_observation_to_evidence(
            result, image_identifier=identifier, evidence_id=evidence_id,
            timestamp=self._data.initial_snapshot.timestamp, reliability=self._reliability,
            sam_evidence_ids=sam.evidence_ids if sam is not None else [],
        )
        self._ledger.add(record)
        self._next_evidence_number += 1
        response = VisualConditionToolResult(
            status="completed", component=result.component, observations=result.observations,
            image_quality=result.image_quality, evidence_ids=[evidence_id], evidence_ids_added=[evidence_id],
        )
        self._condition_results[request.component] = response.model_copy(deep=True)
        return response
