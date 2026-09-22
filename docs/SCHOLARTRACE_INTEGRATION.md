# ScholarTrace Integration

Current application source candidate version: **3.1.0**. The retrieval contract stays Schema `1.0` / `dense-v1`; historical 2.x integration results below are not a new 3.1.0 live integration test. Check Consumer service-version constraints and use the [migration guide](MIGRATION_3_0.md).

## Compatibility

DocuMind 3.1.0 source candidate provides `POST /api/v1/retrieve` for ScholarTrace and other
trusted local Consumers. The public contract remains Schema `1.0` with
retrieval version `dense-v1`. The bounded execution, retrieval-specific
readiness and observability introduced in v2.2.0 remain in place; the
application version change does not widen retrieval scope or alter fields.

Use the checked-in Provider artifacts as the source of truth:

- `contracts/retrieve-v1.schema.json`: strict request, response and error JSON
  Schema objects;
- `contracts/retrieve-v1.fixtures.json`: valid and invalid cross-repository
  Consumer examples.

Consumers must reject unsupported Schema versions and must never parse
`/chat/stream` output as evidence.

## Request Sequence

1. Read `GET /api/v1/health/ready` and inspect `components.retrieval`. If the
   Embedding model was unloaded after idle time, issue one bounded warm-up with
   the configured `OLLAMA_EMBEDDING_KEEP_ALIVE_SECONDS` and recheck readiness;
   do not treat this as model deletion.
2. Obtain a `document_key` and its current `active_index_id` from the upload or
   document-detail response.
3. Send one document and the captured index identity to `/retrieve`.
4. Verify Schema `1.0`, the returned document/index identities, contiguous
   ranks and each `content_sha256` before evidence enters an agent context.
5. Preserve `chunk_id`, `source`, `page_number`, `rank` and distance with every
   downstream claim so ScholarTrace can cite the original evidence.

The readiness endpoint can return HTTP 503 when the LLM is unavailable while
`components.retrieval` is still `ready`. This state permits `/retrieve` but not
`/chat/stream`. A missing or non-ready retrieval component must fail closed.

## Python Consumer Example

```python
from __future__ import annotations

import hashlib
from typing import Any

import httpx


def retrieve_evidence(
    client: httpx.Client,
    *,
    query: str,
    document_key: str,
    expected_index_id: str,
    traceparent: str | None = None,
) -> dict[str, Any]:
    headers = {"traceparent": traceparent} if traceparent else {}
    response = client.post(
        "/api/v1/retrieve",
        headers=headers,
        json={
            "schema_version": "1.0",
            "query": query,
            "document_key": document_key,
            "expected_index_id": expected_index_id,
            "top_k": 5,
            "retrieval_mode": "dense",
            "distance_threshold": None,
        },
    )
    if response.status_code == 409:
        code = response.json().get("error", {}).get("code")
        if code == "stale_document_index":
            raise RuntimeError("refresh active_index_id before retrying")
    response.raise_for_status()
    payload = response.json()
    if payload.get("schema_version") != "1.0":
        raise RuntimeError("unsupported DocuMind retrieval Schema")
    if payload.get("document_key") != document_key:
        raise RuntimeError("DocuMind returned evidence from another document")
    if payload.get("index_id") != expected_index_id:
        raise RuntimeError("DocuMind returned evidence from another index")
    for rank, chunk in enumerate(payload.get("chunks", []), start=1):
        digest = hashlib.sha256(chunk["content"].encode("utf-8")).hexdigest()
        if chunk.get("rank") != rank or chunk.get("content_sha256") != digest:
            raise RuntimeError("invalid DocuMind evidence integrity")
    return payload


with httpx.Client(base_url="http://127.0.0.1:8001", timeout=20.0) as client:
    evidence = retrieve_evidence(
        client,
        query="What evidence supports this claim?",
        document_key="a" * 64,
        expected_index_id="b" * 64,
    )
```

Production Consumers should additionally validate successful and error payloads
against the matching objects in `retrieve-v1.schema.json`. Do not log the query,
Chunk content, complete identities or authorization data.

## Error Handling

| Result | Consumer action |
|---|---|
| 200 with Chunks | Validate identities, integrity and ranks, then retain evidence metadata |
| 200 with `chunks: []` | Treat as no evidence; do not fall back to generated text |
| `stale_document_index` | Refresh document detail and retry once with the new active index |
| Lifecycle 409 other than stale | Wait for the document operation to finish; do not change scope |
| `retrieval_capacity_exceeded` | Apply bounded jittered backoff at the workflow boundary |
| `retrieval_timeout` or unavailable | Surface dependency failure; avoid unbounded nested retries |
| 404 or 422 | Treat as terminal input/contract failure |

DocuMind already performs at most the configured safe dependency attempts.
ScholarTrace retries must have their own small total budget and must preserve the
same document scope unless a stale-index response explicitly requires refresh.

For local Ollama deployments, `OLLAMA_EMBEDDING_KEEP_ALIVE_SECONDS` defaults to
600 seconds and is sent on both readiness and retrieval Embedding requests. The
setting is bounded to `0-3600`; the separate
`OLLAMA_EMBEDDING_READINESS_TIMEOUT_SECONDS` defaults to 60 seconds so a cold
load can complete within a bounded health-check window. `0` favors prompt model
turnover but makes the next retrieval susceptible to cold-load latency, while a
longer value consumes more GPU residency and still does not guarantee that Ollama
can keep the model loaded under memory pressure.

## Operational Smoke Test

The following PowerShell flow uploads a repository fixture, confirms the active
index, retrieves evidence and removes only a document that was absent before
the test:

```powershell
$base = "http://127.0.0.1:8001/api/v1"
$before = Invoke-RestMethod "$base/documents"
$upload = curl.exe -fsS -F "file=@tests/knowledge_base.txt;type=text/plain" `
  "$base/documents" | ConvertFrom-Json
$wasPresent = $before.items.document_key -contains $upload.document_key
$detail = Invoke-RestMethod "$base/documents/$($upload.document_key)"
if ($detail.status -ne "active" -or -not $detail.active_index_id) {
  throw "uploaded document is not active"
}
$request = @{
  schema_version = "1.0"
  query = "监督学习有哪些主要算法？"
  document_key = $detail.document_key
  expected_index_id = $detail.active_index_id
  top_k = 3
  retrieval_mode = "dense"
  distance_threshold = $null
} | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri "$base/retrieve" `
  -ContentType "application/json" -Body $request
if ($result.schema_version -ne "1.0" -or $result.chunks.Count -lt 1) {
  throw "pure retrieval smoke test failed"
}
if (-not $wasPresent) {
  Invoke-RestMethod -Method Delete "$base/documents/$($upload.document_key)"
}
```

Run this against an isolated test deployment before enabling ScholarTrace. Keep
the fixture, response and logs out of any report that could expose real user
content.

## Historical Version Compatibility

The historical v2.1.0-to-v2.2.0 transition did not require a Registry or Milvus migration. This does not establish compatibility for arbitrary later changes. Deploy the
candidate, inspect `components.retrieval`, run the smoke path, then enable
Consumer traffic. Existing upload, lifecycle and chat contracts are unchanged.

Rolling back to v2.1.0 retains `/retrieve` Schema `1.0`, but loses v2.2.0's
bounded execution policy, retrieval readiness, dedicated metrics and inbound
Trace Context. Drain retrieval traffic before rollback and restore the previous
application version against the same Registry and Milvus data. Rolling back to
v2.0.8 removes `/retrieve`; disable all Consumers before that rollback.

## Service Boundary

- trusted local/private-network Consumers only; there is no public auth or
  per-tenant authorization boundary;
- one document and one expected active index per request;
- Dense L2 only, with no online Hybrid, Reranker, Rewrite or result cache;
- no batch API, MCP surface, asynchronous retrieval job or conversation state;
- no LLM call and no answer synthesis;
- no globally recommended distance threshold; calibrate per embedding space and
  corpus before configuring one;
- evidence content may be sensitive and must follow the source document's data
  handling policy.
