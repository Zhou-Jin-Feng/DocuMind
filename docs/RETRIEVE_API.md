# Pure Retrieval API

## Status

This document describes Schema `1.0` for the single-document Dense retrieval
Provider. `service_version` identifies the deployed application version; it is
independent of the retrieval Schema and does not attest to deployment validation.

## Endpoint

```http
POST /api/v1/retrieve
Content-Type: application/json
```

The endpoint returns source Chunks only. It never calls the answer-generation
model and never treats `/chat/stream` output as source evidence.

## Request

```json
{
  "schema_version": "1.0",
  "query": "What evidence supports the claim?",
  "document_key": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expected_index_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "top_k": 3,
  "retrieval_mode": "dense",
  "distance_threshold": null
}
```

All fields except `distance_threshold` are required. Unknown fields are
rejected. `query` is trimmed and limited to 4,000 characters. Document and index
identities are lowercase 64-character SHA-256 values. `top_k` is between 1 and
20. The JSON request body is limited to 16 KiB. Schema `1.0` accepts only
`dense` retrieval.

`distance_threshold`, when present, is the maximum accepted Milvus L2 distance.
L2 distance is lower-is-more-relevant and must not be interpreted as a
similarity score. A threshold calibrated for another Embedding space must not be
reused without evaluation.

## Success Response

```json
{
  "schema_version": "1.0",
  "service_version": "3.1.0",
  "retrieval_version": "dense-v1",
  "retrieval_mode": "dense",
  "document_key": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "index_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "source_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "chunks": [
    {
      "chunk_id": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "content": "A retrieved evidence chunk.",
      "content_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "source": "paper.pdf",
      "page_number": 3,
      "distance": 0.42,
      "rank": 1
    }
  ]
}
```

A valid query with no retained Chunk returns HTTP `200` with `chunks: []`. The
response exposes only the fields above; arbitrary Milvus metadata and absolute
source paths are not part of the contract.

## Error Envelope

```json
{
  "error": {
    "code": "stale_document_index",
    "message": "The requested document index is no longer active.",
    "request_id": "request-1234"
  }
}
```

The interface uses these status families:

| HTTP | Machine code | Meaning |
|---|---|---|
| 404 | `document_not_found` | Document is unknown in the current scope |
| 409 | `stale_document_index` | Expected index differs from the active index |
| 409 | `document_index_unavailable` | Document has no retrievable active index |
| 409 | `document_operation_in_progress` | Deletion or index transition prevents retrieval |
| 413 | `request_too_large` | JSON request body exceeds 16 KiB |
| 422 | `validation_error` | Request does not satisfy Schema `1.0` |
| 503 | `retrieval_capacity_exceeded` | Bounded retrieval capacity was not acquired in time |
| 503 | `retrieval_timeout` | Embedding or Milvus exceeded its bounded timeout attempts |
| 503 | `retrieval_service_unavailable` | Embedding, Milvus, Registry or service is unavailable |

## Compatibility

Schema `1.x` may add optional response fields and new documented error codes.
Removing fields, changing field meaning, widening retrieval scope, changing L2
semantics, or accepting multiple documents requires a new major Schema version.
A Consumer must reject unsupported Schema versions and must not fall back to
`/chat/stream`.

## Retrieval Readiness

Read `GET /api/v1/health/ready` and inspect `components.retrieval`. The endpoint
can return HTTP 503 because generation is unavailable while retrieval remains
`ready`; this state permits `/retrieve` but not `/chat/stream`. Consumers must
fail closed when the retrieval component is absent or not ready.

## Application 3.1.0 candidate

The current source candidate reports `service_version: 3.1.0`; the retrieval contract remains
Schema `1.0` and `retrieval_version: dense-v1`. The Gradio launcher and legacy
server settings are removed, and default local paths are rooted in the project.
Review [the migration guide](MIGRATION_3_0.md) before changing deployments.
An unchanged retrieval Schema does not prove that an older deployment layout or
Consumer version pin is automatically compatible.

## Historical Version Compatibility

Upgrading from v2.1.0 to v2.2.0 requires no Registry or Milvus migration and
does not alter existing request or response fields. Deploy the candidate, check
retrieval readiness, run an upload/status/retrieve smoke path, then enable
Consumer traffic.

Rolling back to v2.1.0 retains Schema `1.0` but loses the v2.2.0 bounded
execution policy, retrieval-specific readiness and observability. Drain
retrieval traffic before switching versions. Rolling back to v2.0.8 removes the
route entirely, so disable `/retrieve` Consumers first. Both rollback targets
reuse the same Registry and Milvus data; no persistent Schema removal is needed.

The checked-in Provider/Consumer artifacts are
`docs/contracts/retrieve-v1.schema.json` and
`docs/contracts/retrieve-v1.fixtures.json`. Consumers should validate the
shared valid and invalid fixtures directly against the JSON Schema rather than
importing DocuMind Python models.

The end-to-end ScholarTrace sequence, Consumer example, smoke test and service
boundary are documented in [ScholarTrace Integration](SCHOLARTRACE_INTEGRATION.md).

## Resource Controls

Pure retrieval uses separate connection, Embedding and Milvus query timeouts.
Concurrent requests are bounded by a process-local semaphore and queue timeout.
Only connection errors, dependency timeouts and explicit HTTP 5xx failures are
retried, at most three attempts by configuration; validation, lifecycle and
scope failures are never retried. Every attempt rechecks the same
`document_key` and `expected_index_id` before search, and the active index is
checked again before evidence is released.

The synchronous dependency call keeps its concurrency permit until it actually
returns, including when the HTTP client disconnects. Provider-native timeouts
bound the remaining work, preventing a cancelled request from releasing a
permit while a shared Milvus or Embedding client is still in use.

When the local Ollama Embedding model has been unloaded after idle time, the
first readiness or retrieval request may pay a cold-load cost. DocuMind sends
the bounded `OLLAMA_EMBEDDING_KEEP_ALIVE_SECONDS` value (default `600`, range
`0-3600`) on both probe and retrieval calls, and gives the readiness probe a
separate `OLLAMA_EMBEDDING_READINESS_TIMEOUT_SECONDS` window (default/max `60`).
Consumers should still warm and recheck `components.retrieval` before a
batch; they must not bypass readiness or treat an unload as deletion of the
installed model.
