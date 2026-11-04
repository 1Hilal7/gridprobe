"""Visible-condition observations; electrical causes are outside this contract."""

import re
import unicodedata
from typing import Annotated, Literal

from pydantic import Field, FiniteFloat, StringConstraints, field_validator, model_validator

from backend.vision.models import Concept, VisionModel, normalize_concept

VISION_MODEL = "muse-spark-1.3"
ImageQuality = Literal["SUFFICIENT", "LIMITED", "INSUFFICIENT"]
ObservationText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=600)]


def validate_observation_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    if any(unicodedata.category(char) == "Cf" for char in normalized):
        raise ValueError("Observation text cannot contain hidden formatting.")
    normalized = re.sub(r"[\s_-]+", " ", normalized)
    forbidden = (
        r"\b(?:loose|looseness|fault\w*|unsafe|safe|danger\w*|failure\w*|defect\w*|diagnos\w*)\b"
        r"|\bover\s*heat\w*\b|\b(?:caused|causes|due to|because of|results? from)\b"
        r"|\b(?:indicates|suggests|proves|confirms|malfunction\w*|recommend\w*|repair\w*)\b"
        r"|hidden ground truth|expected relevant evidence"
    )
    if re.search(forbidden, normalized):
        raise ValueError("Only visible properties are allowed; omit causes, diagnoses, and safety judgments.")
    return text


def normalize_component(value: str) -> str:
    return validate_observation_text(normalize_concept(value))


class VisualObservation(VisionModel):
    feature: ObservationText
    description: ObservationText
    confidence: Annotated[FiniteFloat, Field(ge=0, le=1, strict=True)]

    @field_validator("feature", "description")
    @classmethod
    def descriptive_only(cls, value: str) -> str:
        return validate_observation_text(value)


class VisualObservationResult(VisionModel):
    component: Concept
    observations: Annotated[list[VisualObservation], Field(max_length=20)]
    image_quality: ImageQuality

    @field_validator("component")
    @classmethod
    def component_name(cls, value: str) -> str:
        return normalize_component(value)

    @model_validator(mode="after")
    def insufficient_has_no_findings(self) -> "VisualObservationResult":
        if self.image_quality == "INSUFFICIENT" and self.observations:
            raise ValueError("An insufficient image cannot support condition observations.")
        return self


class VisualConditionToolResult(VisionModel):
    status: Literal["completed", "unavailable", "error"]
    component: str
    observations: list[VisualObservation] = Field(default_factory=list)
    image_quality: ImageQuality | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_ids_added: list[str] = Field(default_factory=list)
    error_code: str | None = None
    message: str | None = None
