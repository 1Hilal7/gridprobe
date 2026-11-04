"""Shared Muse Spark Standard pricing defaults and project overrides."""

import os
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, model_validator


TOKENS_PER_MILLION = 1_000_000
# Standard mode, USD / 1M tokens: https://dev.meta.ai/docs/pricing-rate-limits
STANDARD_INPUT_PRICE_PER_MILLION = 1.25
STANDARD_OUTPUT_PRICE_PER_MILLION = 4.25
TokenPrice = Annotated[FiniteFloat, Field(ge=0)]


class EvaluationConfigurationError(ValueError):
    """Evaluation pricing configuration is invalid or incomplete."""


class PricingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    input_price_per_million: TokenPrice | None = STANDARD_INPUT_PRICE_PER_MILLION
    output_price_per_million: TokenPrice | None = STANDARD_OUTPUT_PRICE_PER_MILLION
    currency: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = "USD"

    @model_validator(mode="after")
    def require_price_pair(self) -> Self:
        if (self.input_price_per_million is None) != (self.output_price_per_million is None):
            raise ValueError("Configure both input and output prices, or leave both unset.")
        return self

    @classmethod
    def from_env(cls) -> "PricingConfig":
        try:
            input_price = os.environ.get("META_INPUT_PRICE_PER_MILLION") or None
            output_price = os.environ.get("META_OUTPUT_PRICE_PER_MILLION") or None
            currency = os.environ.get("META_PRICE_CURRENCY", "USD")
            if input_price is None and output_price is None:
                if currency != "USD":
                    raise ValueError("USD default prices cannot be labeled as another currency.")
                return cls()
            return cls(
                input_price_per_million=input_price,
                output_price_per_million=output_price,
                currency=currency,
            )
        except ValueError:
            raise EvaluationConfigurationError(
                "Configure finite, nonnegative META_INPUT_PRICE_PER_MILLION and "
                "META_OUTPUT_PRICE_PER_MILLION together. Standard defaults use USD."
            ) from None
