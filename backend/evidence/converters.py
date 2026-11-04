"""Convert retrieved data and numerical outputs into uninterpreted observations."""

from datetime import datetime

from backend.evidence.models import EvidenceRecord, EvidenceSource, EvidenceType
from backend.scenarios.models import MaintenanceContext
from backend.tools.electrical import PhaseImbalanceResult, TemperatureTrendResult
from backend.tools.models import Sensor, SensorHistoryResult
from backend.vision.models import SegmentationResult
from backend.vision.observation_models import VISION_MODEL, VisualObservationResult


def phase_imbalance_to_evidence(
    result: PhaseImbalanceResult,
    *,
    evidence_id: str,
    timestamp: datetime,
    reliability: float,
) -> EvidenceRecord:
    """Preserve the measured imbalance and its numerical context."""
    return EvidenceRecord(
        id=evidence_id,
        source=EvidenceSource.DETERMINISTIC_ANALYSIS,
        type=EvidenceType.PHASE_IMBALANCE,
        timestamp=timestamp,
        summary="Phase-current imbalance calculated from the maximum deviation from the mean.",
        value=result.imbalance_percent,
        unit="percent",
        tool_name="calculate_phase_imbalance",
        reliability=reliability,
        metadata={
            "most_deviant_phase": result.most_deviant_phase,
            "average_current": result.average_current,
            "max_deviation": result.max_deviation,
        },
    )


def temperature_trend_to_evidence(
    result: TemperatureTrendResult,
    *,
    evidence_id: str,
    timestamp: datetime,
    reliability: float,
) -> EvidenceRecord:
    """Preserve signed temperature change, endpoints, duration, and rate."""
    return EvidenceRecord(
        id=evidence_id,
        source=EvidenceSource.HISTORY,
        type=EvidenceType.TEMPERATURE_TREND,
        timestamp=timestamp,
        summary="Signed temperature change calculated from chronological endpoint measurements.",
        value=result.temperature_change,
        unit="celsius",
        tool_name="calculate_temperature_trend",
        reliability=reliability,
        metadata={
            "start_temperature": result.start_temperature,
            "end_temperature": result.end_temperature,
            "duration_minutes": result.duration_minutes,
            "rate_per_minute": result.rate_per_minute,
        },
    )


_HISTORY_TYPES_AND_UNITS: dict[Sensor, tuple[EvidenceType, str]] = {
    "current_a": (EvidenceType.CURRENT_HISTORY, "amperes"),
    "current_b": (EvidenceType.CURRENT_HISTORY, "amperes"),
    "current_c": (EvidenceType.CURRENT_HISTORY, "amperes"),
    "voltage_a": (EvidenceType.VOLTAGE_HISTORY, "volts"),
    "voltage_b": (EvidenceType.VOLTAGE_HISTORY, "volts"),
    "voltage_c": (EvidenceType.VOLTAGE_HISTORY, "volts"),
    "temperature": (EvidenceType.TEMPERATURE_HISTORY, "celsius"),
}


def sensor_history_to_evidence(
    result: SensorHistoryResult,
    *,
    evidence_id: str,
    timestamp: datetime,
    reliability: float,
) -> EvidenceRecord:
    """Preserve the exact retrieved series in its chronological retrieval order.

    Series evidence has no single scalar value, so value is null. Empty
    retrievals retain a zero count and null statistics/endpoints rather than
    fabricating measurements. The record timestamp is supplied by the caller;
    the series' actual time bounds are recorded separately in metadata.
    """
    evidence_type, unit = _HISTORY_TYPES_AND_UNITS[result.sensor]
    points = result.model_dump(mode="json")["points"]
    values = [point.value for point in result.points]
    return EvidenceRecord(
        id=evidence_id, source=EvidenceSource.HISTORY, type=evidence_type,
        timestamp=timestamp,
        summary=f"Retrieved {len(points)} timestamped measurements for {result.sensor}.",
        value=None, unit=unit, tool_name="get_sensor_history", reliability=reliability,
        metadata={
            "panel_id": result.panel_id,
            "sensor": result.sensor,
            "requested_minutes": result.minutes,
            "first_value": values[0] if values else None,
            "last_value": values[-1] if values else None,
            "minimum_value": min(values) if values else None,
            "maximum_value": max(values) if values else None,
            "number_of_points": len(points),
            "start_timestamp": points[0]["timestamp"] if points else None,
            "end_timestamp": points[-1]["timestamp"] if points else None,
            "points": points,
        },
    )


def maintenance_context_to_evidence(
    context: MaintenanceContext,
    *,
    evidence_id: str,
    timestamp: datetime,
    reliability: float,
) -> EvidenceRecord:
    """Preserve recorded maintenance information verbatim, including unknowns."""
    return EvidenceRecord(
        id=evidence_id, source=EvidenceSource.MAINTENANCE_CONTEXT, type=EvidenceType.MAINTENANCE_NOTE,
        timestamp=timestamp, summary="Retrieved recorded maintenance context.",
        value=context.recent_maintenance_note, unit=None, tool_name="get_maintenance_context",
        reliability=reliability, metadata=context.model_dump(mode="json"),
    )


def visual_segmentation_to_evidence(
    result: SegmentationResult, *, image_identifier: str, evidence_id: str,
    timestamp: datetime, reliability: float,
) -> EvidenceRecord:
    """Localizations only. An empty completed match is also an observation."""
    return EvidenceRecord(
        id=evidence_id, source=EvidenceSource.VISION,
        type=EvidenceType.VISUAL_COMPONENT_OBSERVATION, timestamp=timestamp,
        summary=f"Component segmentation returned {result.objects_found} objects for {result.concept}.",
        value=result.objects_found, unit="objects", tool_name="inspect_component_image",
        reliability=reliability, metadata={
            "concept": result.concept, "objects_found": result.objects_found,
            "boxes": [box.model_dump(mode="json") for box in result.boxes],
            "mask_count": len(result.masks),
            "masks": [mask.model_dump(mode="json") for mask in result.masks],
            "image_identifier": image_identifier, "sam_model": result.model,
            "image_width": result.image_width, "image_height": result.image_height,
            "coordinate_system": "source_image_pixels_half_open",
        },
    )


def visual_observation_to_evidence(
    result: VisualObservationResult, *, image_identifier: str, evidence_id: str,
    timestamp: datetime, reliability: float, sam_evidence_ids: list[str],
) -> EvidenceRecord:
    """Preserve descriptive observations and quality; never infer a cause."""
    result = VisualObservationResult.model_validate(result.model_dump())
    summary = " ".join(observation.description for observation in result.observations)
    return EvidenceRecord(
        id=evidence_id, source=EvidenceSource.VISION,
        type=EvidenceType.VISUAL_COMPONENT_OBSERVATION, timestamp=timestamp,
        summary=summary or "Image quality does not provide recorded component condition observations.",
        value=None, unit=None, tool_name="inspect_visual_condition", reliability=reliability,
        metadata={**result.model_dump(mode="json"), "vision_model": VISION_MODEL,
                  "image_identifier": image_identifier, "sam_evidence_ids": list(sam_evidence_ids)},
    )
