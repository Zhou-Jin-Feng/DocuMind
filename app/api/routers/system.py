"""Non-sensitive runtime configuration exposed to the frontend."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_application
from app.api.schemas import PublicConfigResponse
from app.application import RAGApplication
from app.core.embedding_client import UniversalEmbeddingClient

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/config", response_model=PublicConfigResponse)
def public_config(
    application: RAGApplication = Depends(get_application),
) -> PublicConfigResponse:
    app_settings = application.settings
    embedding = UniversalEmbeddingClient.configuration_for(
        app_settings.default_embedding_provider
    )
    return PublicConfigResponse(
        embedding_provider=app_settings.default_embedding_provider,
        embedding_model=str(embedding["model"]),
        llm_provider=app_settings.default_llm_provider,
        collection_name=app_settings.collection_name,
        allowed_extensions=app_settings.allowed_extensions,
        max_upload_size_mb=app_settings.max_upload_size_mb,
        retrieval_top_k=app_settings.retrieval_top_k,
    )
