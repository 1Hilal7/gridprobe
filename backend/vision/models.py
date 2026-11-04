"""Application geometry contracts, independent of the SAM token protocol."""

from typing import Annotated, Literal
import re

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, field_validator, model_validator

SAM_MODEL = "sam-3.1"
Concept = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80)]


def normalize_concept(value: str) -> str:
    # A lexical guard, not an NLP classifier: reject instructions and causal claims.
    phrase = " ".join(value.lower().split())
    if not re.fullmatch(r"[a-z]+(?:[ -][a-z]+){0,5}", phrase):
        raise ValueError("Use a short concrete noun phrase of up to six words.")
    forbidden = {"dangerous", "faulty", "overheating", "loose", "diagnose", "ignore", "instructions", "fault", "unsafe"}
    if forbidden.intersection(re.split(r"[ -]", phrase)):
        raise ValueError("Request a component name, without condition or instruction language.")
    return phrase


class VisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ConceptRequest(VisionModel):
    concept: Concept

    @field_validator("concept")
    @classmethod
    def validate_concept(cls, value: str) -> str:
        return normalize_concept(value)


class ComponentBox(VisionModel):
    object_id: str
    left: Annotated[FiniteFloat, Field(ge=0)]
    top: Annotated[FiniteFloat, Field(ge=0)]
    right: Annotated[FiniteFloat, Field(gt=0)]
    bottom: Annotated[FiniteFloat, Field(gt=0)]


class MaskMetadata(VisionModel):
    object_id: str
    encoding: Literal["lossless", "one_bit"]
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class SamDiagnostic(VisionModel):
    severity: Literal["warning", "error"]
    line: int
    # Deliberately omit message/raw: parser messages may echo external text.


class SegmentationResult(ConceptRequest):
    model: Literal["sam-3.1"] = SAM_MODEL
    status: Literal["completed"] = "completed"
    completed: Literal[True] = True
    objects_found: Annotated[int, Field(ge=0)]
    image_width: Annotated[int, Field(gt=0)]
    image_height: Annotated[int, Field(gt=0)]
    boxes: list[ComponentBox]
    masks: list[MaskMetadata]
    diagnostics: list[SamDiagnostic] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_geometry(self) -> "SegmentationResult":
        if self.objects_found != len({item.object_id for item in [*self.boxes, *self.masks]}):
            raise ValueError("Object count must match the returned object identifiers.")
        for box in self.boxes:
            if box.right <= box.left or box.bottom <= box.top or box.right > self.image_width or box.bottom > self.image_height:
                raise ValueError("Box coordinates must lie within the displayed image bounds.")
        return self


class VisualToolResult(VisionModel):
    status: Literal["completed", "unavailable", "error"]
    concept: str
    objects_found: int | None = None
    boxes: list[ComponentBox] = Field(default_factory=list)
    mask_count: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    image_identifier: str | None = None
    model: Literal["sam-3.1"] = SAM_MODEL
    evidence_ids_added: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None
    message: str | None = None
