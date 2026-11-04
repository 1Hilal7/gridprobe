"""FastAPI entry point for the GridProbe backend."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Public health-check response."""

    status: Literal["ok"] = "ok"
    service: Literal["gridprobe-backend"] = "gridprobe-backend"


app = FastAPI(title="GridProbe Backend")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the backend is running."""
    return HealthResponse()
