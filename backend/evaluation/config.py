"""Project-supplied pricing; no published API prices are inferred."""

import os
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, ValidationError, model_validator


TOKENS_PER_MILLION = 1_000_000
TokenPrice = Annotated[FiniteFloat, Field(ge=0)]


class EvaluationConfigurationError(ValueError):
    """Evaluation pricing configuration is invalid or incomplete."""


class PricingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    input_price_per_million: TokenPrice | None = None
    output_price_per_million: TokenPrice | None = None
    currency: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = "USD"

    @model_validator(mode="after")
    def require_price_pair(self) -> Self:
        if (self.input_price_per_million is None) != (self.output_price_per_million is None):
            raise ValueError("Configure both input and output prices, or leave both unset.")
        return self

    @classmethod
    def from_env(cls) -> "PricingConfig":
        try:
            return cls(
                input_price_per_million=os.environ.get("META_INPUT_PRICE_PER_MILLION") or None,
                output_price_per_million=os.environ.get("META_OUTPUT_PRICE_PER_MILLION") or None,
                currency=os.environ.get("META_PRICE_CURRENCY", "USD"),
            )
        except ValidationError:
            raise EvaluationConfigurationError(
                "Configure finite, nonnegative META_INPUT_PRICE_PER_MILLION and "
                "META_OUTPUT_PRICE_PER_MILLION together, and a nonempty META_PRICE_CURRENCY."
            ) from None
