"""Versioned single-document pure retrieval endpoint."""

from fastapi import APIRouter, Depends

from app import __version__
from app.api.dependencies import get_retrieval_service
from app.api.errors import APIError
from app.api.schemas import (
    RETRIEVAL_VERSION,
    RETRIEVE_SCHEMA_VERSION,
    ErrorResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from app.services.retrieval_service import (
    DocumentIndexUnavailableError,
    DocumentNotFoundError,
    DocumentOperationInProgressError,
    RetrievalBusyError,
    RetrievalDependencyTimeoutError,
    RetrievalService,
    StaleDocumentIndexError,
)

router = APIRouter(tags=["retrieval"])


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def retrieve_document(
    payload: RetrieveRequest,
    service: RetrievalService = Depends(get_retrieval_service),
) -> RetrieveResponse:
    try:
        batch = service.retrieve(
            payload.query,
            document_key=payload.document_key,
            expected_index_id=payload.expected_index_id,
            top_k=payload.top_k,
            retrieval_mode=payload.retrieval_mode,
            distance_threshold=payload.distance_threshold,
        )
    except DocumentNotFoundError as exc:
        raise APIError(404, "document_not_found", "未找到该文档。") from exc
    except StaleDocumentIndexError as exc:
        raise APIError(
            409,
            "stale_document_index",
            "请求的文档索引已不是当前活动索引。",
        ) from exc
    except DocumentOperationInProgressError as exc:
        raise APIError(
            409,
            "document_operation_in_progress",
            "该文档正在执行索引或删除操作，请稍后重试。",
        ) from exc
    except DocumentIndexUnavailableError as exc:
        raise APIError(
            409,
            "document_index_unavailable",
            "该文档当前没有可用于检索的活动索引。",
        ) from exc
    except RetrievalBusyError as exc:
        raise APIError(
            503,
            "retrieval_capacity_exceeded",
            "检索服务当前繁忙，请稍后重试。",
        ) from exc
    except RetrievalDependencyTimeoutError as exc:
        raise APIError(
            503,
            "retrieval_timeout",
            "检索依赖响应超时，请稍后重试。",
        ) from exc
    except ValueError as exc:
        raise APIError(422, "validation_error", "检索请求不符合接口约束。") from exc
    except Exception as exc:
        raise APIError(
            503,
            "retrieval_service_unavailable",
            "检索服务暂时不可用，请稍后重试。",
        ) from exc
    return RetrieveResponse(
        schema_version=RETRIEVE_SCHEMA_VERSION,
        service_version=__version__,
        retrieval_version=RETRIEVAL_VERSION,
        retrieval_mode=payload.retrieval_mode,
        **batch.to_dict(),
    )
