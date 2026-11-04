"""Local product settings and centralized Muse Spark Standard pricing."""

import os

from backend.evaluation.config import PricingConfig


def product_pricing() -> PricingConfig:
    configured = PricingConfig.from_env()
    if configured.currency != "USD":
        raise ValueError("The product API requires USD prices.")
    return configured


def frontend_origins() -> list[str]:
    return [origin.strip() for origin in os.environ.get(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
    ).split(",") if origin.strip()]
