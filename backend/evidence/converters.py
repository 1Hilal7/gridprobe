"""Convert numerical tool outputs to observations without interpreting faults."""

from datetime import datetime

from backend.evidence.models import EvidenceRecord, EvidenceSource, EvidenceType
from backend.tools.electrical import PhaseImbalanceResult, TemperatureTrendResult


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
