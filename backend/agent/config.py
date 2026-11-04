"""Environment-only Meta configuration; importing this module reads no secrets."""

import os
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, ValidationError, field_validator

from backend.agent.errors import MissingMetaAPIKeyError, MuseConfigurationError


META_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_META_MODEL = "muse-spark-1.3"


class MetaConfig(BaseModel):
    """Validated configuration with credentials excluded from dumps and repr."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    api_key: SecretStr = Field(exclude=True, repr=False)
    model: Annotated[str, StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")] = DEFAULT_META_MODEL
    base_url: Literal["https://api.meta.ai/v1"] = META_BASE_URL

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value()
        if not key or any(not 33 <= ord(character) <= 126 for character in key):
            raise ValueError("META_API_KEY must contain non-whitespace printable ASCII characters")
        return value

    @classmethod
    def from_env(cls) -> "MetaConfig":
        """Read only META_API_KEY/META_MODEL; never read a .env file or SDK key."""
        key = os.environ.get("META_API_KEY")
        if key is None or not key.strip():
            raise MissingMetaAPIKeyError("Set META_API_KEY to use the Meta Model API.")
        try:
            return cls(api_key=SecretStr(key), model=os.environ.get("META_MODEL", DEFAULT_META_MODEL))
        except ValidationError:
            raise MuseConfigurationError(
                "Invalid Meta provider configuration: check META_MODEL and the format of META_API_KEY."
            ) from None
