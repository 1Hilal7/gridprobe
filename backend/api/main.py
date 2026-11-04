"""FastAPI entry point for the GridProbe backend."""

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.api.config import frontend_origins
from backend.api.models import InvestigationRequest, InvestigationResponse, ScenarioSummary
from backend.api.service import ProductAPIError, demo_image_path, list_demo_scenarios, run_investigation
from backend.vision.errors import SamImageError
from backend.vision.provider import read_image


class HealthResponse(BaseModel):
    """Public health-check response."""

    status: Literal["ok"] = "ok"
    service: Literal["gridprobe-backend"] = "gridprobe-backend"


app = FastAPI(title="GridProbe Backend")
app.add_middleware(
    CORSMiddleware, allow_origins=frontend_origins(), allow_credentials=False,
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)


@app.exception_handler(ProductAPIError)
async def product_error_handler(request: Request, exc: ProductAPIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": {
        "code": exc.code, "message": exc.message, "retryable": exc.retryable,
    }})


@app.exception_handler(RequestValidationError)
async def request_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {
        "code": "INVALID_REQUEST", "message": "Provide a request containing only a valid case_id.", "retryable": False,
    }})


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the backend is running."""
    return HealthResponse()


@app.get("/api/scenarios", response_model=list[ScenarioSummary])
def scenarios() -> list[ScenarioSummary]:
    return list_demo_scenarios()


@app.get("/api/scenarios/{case_id}/image", response_class=FileResponse)
def scenario_image(case_id: str) -> FileResponse:
    path = demo_image_path(case_id)
    try:
        data_url, _, _ = read_image(path)
    except SamImageError:
        raise ProductAPIError(404, "IMAGE_UNAVAILABLE", "The demo image is unavailable.") from None
    return FileResponse(path, media_type=data_url.split(";", 1)[0][5:],
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@app.post("/api/investigations", response_model=InvestigationResponse)
def investigate(request: InvestigationRequest) -> InvestigationResponse:
    return run_investigation(request.case_id)
