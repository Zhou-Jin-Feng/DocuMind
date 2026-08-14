"""Document upload and registry endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.dependencies import get_application, get_document_service
from app.api.errors import APIError
from app.api.schemas import (
    DocumentListResponse,
    ErrorResponse,
    IngestionResponse,
)
from app.application import RAGApplication
from app.lifecycle.service import IndexOperationInProgress
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
def list_documents(
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    items = [record.to_dict() for record in service.list_documents()]
    return DocumentListResponse(items=items, total=len(items))


@router.post(
    "",
    response_model=IngestionResponse,
    responses={
        409: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def upload_document(
    file: UploadFile = File(...),
    application: RAGApplication = Depends(get_application),
    service: DocumentService = Depends(get_document_service),
) -> IngestionResponse:
    display_name = Path(file.filename or "").name.strip()
    if not display_name or display_name in {".", ".."}:
        raise APIError(422, "invalid_filename", "上传文件名无效。")

    extension = Path(display_name).suffix.lower()
    if extension not in application.settings.allowed_extensions:
        raise APIError(
            415,
            "unsupported_file_type",
            "仅支持 PDF、DOCX 和 TXT 文件。",
        )

    max_bytes = application.settings.max_upload_size_mb * 1024 * 1024
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="rag-upload-",
            suffix=extension,
            delete=False,
        ) as target:
            temporary_path = Path(target.name)
            total_bytes = 0
            while block := file.file.read(1024 * 1024):
                total_bytes += len(block)
                if total_bytes > max_bytes:
                    raise APIError(
                        413,
                        "file_too_large",
                        f"文件不能超过 {application.settings.max_upload_size_mb} MB。",
                    )
                target.write(block)

        result = service.ingest(temporary_path, display_name=display_name)
        return IngestionResponse(**result.to_dict())
    except APIError:
        raise
    except IndexOperationInProgress as exc:
        raise APIError(
            409,
            "index_operation_in_progress",
            "该文档正在建立索引，请稍后重试。",
        ) from exc
    except ValueError as exc:
        raise APIError(422, "document_validation_failed", "文档无法处理。") from exc
    except Exception as exc:
        raise APIError(
            503,
            "document_service_unavailable",
            "文档服务暂时不可用，请查看服务日志。",
        ) from exc
    finally:
        file.file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
