"""Local product settings and centralized Muse Spark Standard pricing."""

import os

from backend.evaluation.config import PricingConfig


# https://dev.meta.ai/docs/pricing-rate-limits (Standard mode, USD / 1M tokens)
STANDARD_INPUT_PRICE_PER_MILLION = 1.25
STANDARD_OUTPUT_PRICE_PER_MILLION = 4.25


def product_pricing() -> PricingConfig:
    configured = PricingConfig.from_env()
    if configured.currency != "USD":
        raise ValueError("The product API requires USD prices.")
    if configured.input_price_per_million is None:
        return PricingConfig(
            input_price_per_million=STANDARD_INPUT_PRICE_PER_MILLION,
            output_price_per_million=STANDARD_OUTPUT_PRICE_PER_MILLION,
        )
    return configured


def frontend_origins() -> list[str]:
    return [origin.strip() for origin in os.environ.get(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
    ).split(",") if origin.strip()]
