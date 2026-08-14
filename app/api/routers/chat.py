"""Streaming question-answer endpoint."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_rag_service
from app.api.schemas import ChatRequest, ErrorResponse
from app.api.sse import encode_stream
from app.services.rag_service import RAGService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "SSE events: status, sources, token, done, error.",
        },
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def stream_chat(
    payload: ChatRequest,
    request: Request,
    service: RAGService = Depends(get_rag_service),
) -> StreamingResponse:
    events = service.stream_answer(
        payload.question,
        request_id=request.state.request_id,
    )
    return StreamingResponse(
        encode_stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
