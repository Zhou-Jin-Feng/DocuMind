"""Server-Sent Event encoding."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

from app.services.rag_service import ChatEvent


def encode_event(event: ChatEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.type}\ndata: {payload}\n\n"


def encode_stream(events: Iterable[ChatEvent]) -> Iterator[str]:
    for event in events:
        yield encode_event(event)
