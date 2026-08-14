"""Liveness and dependency-readiness endpoints."""

from fastapi import APIRouter, Depends, Response, status

from app import __version__
from app.api.dependencies import get_application
from app.api.schemas import HealthResponse
from app.application import RAGApplication

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return HealthResponse(status="alive", version=__version__, ready=True)


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
def readiness(
    response: Response,
    application: RAGApplication = Depends(get_application),
) -> HealthResponse:
    report = application.readiness()
    if not report["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(version=__version__, **report)
