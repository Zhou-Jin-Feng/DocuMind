"""Versioned single-document pure retrieval endpoint."""

from fastapi import APIRouter, Depends

from app import __version__
from app.api.dependencies import get_retrieval_service
from app.api.schemas import (
    RETRIEVAL_VERSION,
    RETRIEVE_SCHEMA_VERSION,
    ErrorResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from app.services.retrieval_service import RetrievalService

router = APIRouter(tags=["retrieval"])


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def retrieve_document(
    payload: RetrieveRequest,
    service: RetrievalService = Depends(get_retrieval_service),
) -> RetrieveResponse:
    batch = service.retrieve(
        payload.query,
        document_key=payload.document_key,
        expected_index_id=payload.expected_index_id,
        top_k=payload.top_k,
        retrieval_mode=payload.retrieval_mode,
        distance_threshold=payload.distance_threshold,
    )
    return RetrieveResponse(
        schema_version=RETRIEVE_SCHEMA_VERSION,
        service_version=__version__,
        retrieval_version=RETRIEVAL_VERSION,
        retrieval_mode=payload.retrieval_mode,
        **batch.to_dict(),
    )
