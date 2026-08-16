"""Liveness and dependency-readiness endpoints."""

from fastapi import APIRouter, Depends, Response, status

from app import __version__
from app.api.dependencies import get_application
from app.api.schemas import HealthResponse
from app.application import RAGApplication

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """只确认 API 进程存活，不访问外部依赖。"""
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
    """返回依赖探活结果；未就绪时使用 503，避免被误判为健康。"""
    report = application.readiness()
    response.headers["Cache-Control"] = "no-store"
    if not report["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(version=__version__, **report)
