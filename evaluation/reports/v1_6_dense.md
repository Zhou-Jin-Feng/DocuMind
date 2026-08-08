# RAG Evaluation Report: demo-golden-dataset

- Cases: 32
- Default Top-K: 3

## Run Configuration

| Setting | Value |
|---|---|
| `baseline_type` | `"deterministic-dense"` |
| `retrieval_mode` | `"dense"` |
| `document_count` | `9` |
| `embedding_provider` | `"evaluation-fake"` |
| `embedding_model` | `"sha256-token-hash-v1"` |
| `embedding_dimension` | `64` |
| `case_count` | `32` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `null` |
| `dataset_sha256` | `"014afc432bb3824a9afb7e361878adb5605dec7e35a2b2a409b777c13f07fb56"` |
| `documents_sha256` | `"552c4de4204bda67ebba4b865d64f6a9ff4862d9dcc745f95993a7342ee10c4d"` |

## Aggregate Metrics

| Metric | Value |
|---|---:|
| `recall_at_k` | 0.2593 |
| `precision_at_k` | 0.0864 |
| `mrr_at_k` | 0.1173 |
| `top_k_hit_rate` | 0.2593 |
| `correct_document_avg_rank` | 2.5714 |
| `no_answer_retrieval_accuracy` | 0.0000 |
| `refusal_accuracy` | 1.0000 |
| `keyword_coverage` | 1.0000 |
| `successful_case_rate` | 1.0000 |
| `average_duration_ms` | 0.4335 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `exact_term` | 6 | 0.0000 | 0.0000 | 0.0000 | N/A | 1.0000 | 0.4379 |
| `hard_negative` | 5 | 0.4000 | 0.1333 | 0.4000 | N/A | 1.0000 | 0.4562 |
| `keyword_precision` | 6 | 0.3333 | 0.2222 | 0.3333 | N/A | 1.0000 | 0.4356 |
| `multi_hop` | 4 | 0.7500 | 0.2917 | 0.7500 | N/A | 1.0000 | 0.3835 |
| `no_answer` | 5 | N/A | N/A | N/A | 0.0000 | 1.0000 | 0.3206 |
| `semantic_paraphrase` | 6 | 0.0000 | 0.0000 | 0.0000 | N/A | 1.0000 | 0.5358 |

## Cases

| Case | Category | Status | Top-K | Duration (ms) |
|---|---|---|---:|---:|
| `exact-rf-001` | `exact_term` | success | 3 | 0.672 |
| `exact-rf-002` | `exact_term` | success | 3 | 0.446 |
| `exact-life-001` | `exact_term` | success | 3 | 0.442 |
| `exact-life-002` | `exact_term` | success | 3 | 0.353 |
| `exact-eval-001` | `exact_term` | success | 3 | 0.353 |
| `exact-embed-001` | `exact_term` | success | 3 | 0.362 |
| `semantic-rf-001` | `semantic_paraphrase` | success | 3 | 0.357 |
| `semantic-rf-002` | `semantic_paraphrase` | success | 3 | 0.534 |
| `semantic-life-001` | `semantic_paraphrase` | success | 3 | 0.601 |
| `semantic-life-002` | `semantic_paraphrase` | success | 3 | 0.391 |
| `semantic-eval-001` | `semantic_paraphrase` | success | 3 | 0.912 |
| `semantic-embed-001` | `semantic_paraphrase` | success | 3 | 0.421 |
| `keyword-config-001` | `keyword_precision` | success | 3 | 0.605 |
| `keyword-config-002` | `keyword_precision` | success | 3 | 0.486 |
| `keyword-config-003` | `keyword_precision` | success | 3 | 0.393 |
| `keyword-config-004` | `keyword_precision` | success | 3 | 0.372 |
| `keyword-config-005` | `keyword_precision` | success | 3 | 0.391 |
| `keyword-config-006` | `keyword_precision` | success | 3 | 0.368 |
| `hard-negative-001` | `hard_negative` | success | 3 | 0.369 |
| `hard-negative-002` | `hard_negative` | success | 3 | 0.361 |
| `hard-negative-003` | `hard_negative` | success | 3 | 0.736 |
| `hard-negative-004` | `hard_negative` | success | 3 | 0.413 |
| `hard-negative-005` | `hard_negative` | success | 3 | 0.402 |
| `multi-hop-001` | `multi_hop` | success | 3 | 0.418 |
| `multi-hop-002` | `multi_hop` | success | 3 | 0.382 |
| `multi-hop-003` | `multi_hop` | success | 3 | 0.376 |
| `multi-hop-004` | `multi_hop` | success | 3 | 0.358 |
| `no-answer-001` | `no_answer` | success | 3 | 0.332 |
| `no-answer-002` | `no_answer` | success | 3 | 0.327 |
| `no-answer-003` | `no_answer` | success | 3 | 0.327 |
| `no-answer-004` | `no_answer` | success | 3 | 0.310 |
| `no-answer-005` | `no_answer` | success | 3 | 0.307 |
