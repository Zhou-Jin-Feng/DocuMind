# Pure Retrieval API

## Status

This document defines the released Schema `1.0` contract for the DocuMind
v2.1.0 single-document Dense retrieval Provider.

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
  "service_version": "2.1.0",
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

The P0 implementation reserves these status families:

| HTTP | Machine code | Meaning |
|---|---|---|
| 404 | `document_not_found` | Document is unknown in the current scope |
| 409 | `stale_document_index` | Expected index differs from the active index |
| 409 | `document_index_unavailable` | Document has no retrievable active index |
| 409 | `document_operation_in_progress` | Deletion or index transition prevents retrieval |
| 413 | `request_too_large` | JSON request body exceeds 16 KiB |
| 422 | `validation_error` | Request does not satisfy Schema `1.0` |
| 503 | `retrieval_service_unavailable` | Embedding, Milvus, Registry or service is unavailable |

## Compatibility

Schema `1.x` may add optional response fields and new documented error codes.
Removing fields, changing field meaning, widening retrieval scope, changing L2
semantics, or accepting multiple documents requires a new major Schema version.
A Consumer must reject unsupported Schema versions and must not fall back to
`/chat/stream`.

## Upgrade And Rollback

Upgrading from v2.0.8 requires no data migration and does not alter existing
document, lifecycle, health or chat contracts. Deploy the v2.1.0 application and
confirm `/api/v1/health/ready` before enabling a Consumer.

To roll back, stop v2.1.0 and start the previous v2.0.8 application against the
same Registry and Milvus data. Disable `/retrieve` Consumers first because the
older service does not provide that route. No new persistent Schema must be
removed during rollback.

The checked-in Provider/Consumer artifact is
`docs/contracts/retrieve-v1.schema.json`.
