"""OpenAI-compatible function definitions, independent of scenario contents."""

from openai.types.chat import ChatCompletionToolParam
from pydantic import BaseModel

from backend.tools.models import HistoryRequest, PanelRequest, TrendRequest, VisualRequest


def get_tool_definitions() -> list[ChatCompletionToolParam]:
    """Return fresh JSON-compatible definitions suitable for MuseProvider.

    Argument schemas are generated from the same models validated by the
    runtime. These definitions neither dispatch tools nor contain scenario data.
    """
    specifications: list[tuple[str, str, type[BaseModel]]] = [
        (
            "get_current_snapshot",
            "Return the active panel's current timestamped voltage, current, and temperature measurements.",
            PanelRequest,
        ),
        (
            "get_sensor_history",
            "Return timestamp/value points for only the selected sensor from stored history, chronologically. "
            "Use a positive lookback in minutes ending at the current snapshot, including both boundaries. "
            "The current snapshot is available separately; an empty window returns an empty points list.",
            HistoryRequest,
        ),
        (
            "calculate_phase_imbalance",
            "Return average current, maximum absolute phase-current deviation, deviation as a percentage "
            "of the average, and the most-deviant phase. A zero average cannot be calculated.",
            PanelRequest,
        ),
        (
            "calculate_temperature_trend",
            "Return start/end temperatures, signed temperature_change in Celsius, duration_minutes, "
            "and rate_per_minute. Use stored history in the positive lookback window plus the current "
            "snapshot. A window with no positive measurement duration cannot be calculated.",
            TrendRequest,
        ),
        (
            "get_maintenance_context",
            "Return only the panel's recorded inspection date, previous alerts, and maintenance note.",
            PanelRequest,
        ),
        (
            "inspect_component_image",
            "If a panel image is supplied, localize a component using SAM 3.1. Supply one short "
            "concrete noun phrase such as electrical terminal. Returns object count, pixel boxes, "
            "mask count, and evidence references only; segmentation does not establish causality. "
            "A completed zero-match is valid. If no image is available, returns a structured unavailable result.",
            VisualRequest,
        ),
    ]
    return [
        {"type": "function", "function": {
            "name": name, "description": description, "strict": True,
            "parameters": model.model_json_schema(),
        }}
        for name, description, model in specifications
    ]
