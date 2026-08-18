# RAG Evaluation Report: demo-golden-dataset

- Cases: 8
- Default Top-K: 3

## Run Configuration

| Setting | Value |
|---|---|
| `baseline_type` | `"deterministic-dense"` |
| `retrieval_mode` | `"dense"` |
| `document_count` | `5` |
| `embedding_provider` | `"evaluation-fake"` |
| `embedding_model` | `"sha256-token-hash-v1"` |
| `embedding_dimension` | `64` |
| `case_count` | `8` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `null` |
| `lexical_score_threshold` | `null` |
| `dense_weight` | `1.0` |
| `lexical_weight` | `1.0` |
| `rrf_k` | `60` |
| `candidate_multiplier` | `5` |
| `dataset_sha256` | `"81741dfc4e4a59698b45ba2565558203aa0f7906c077f98749eb88ce512019a6"` |
| `documents_sha256` | `"645e477edbcd6086226621abb76ddfa147b44acf56c632edf39e89e8220298b3"` |

## Aggregate Metrics

| Metric | Value |
|---|---:|
| `recall_at_k` | 0.8333 |
| `precision_at_k` | 0.2778 |
| `mrr_at_k` | 0.7500 |
| `top_k_hit_rate` | 0.8333 |
| `correct_document_avg_rank` | 1.2000 |
| `no_answer_retrieval_accuracy` | 0.0000 |
| `refusal_accuracy` | 1.0000 |
| `keyword_coverage` | 1.0000 |
| `successful_case_rate` | 1.0000 |
| `average_duration_ms` | 0.6165 |
| `p50_duration_ms` | 0.5988 |
| `p95_duration_ms` | 0.9421 |
| `maximum_duration_ms` | 0.9872 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `general` | 8 | 0.8333 | 0.7500 | 0.8333 | 0.0000 | 1.0000 | 0.6165 | 0.5988 | 0.9421 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `all` | 8 | 0.8333 | 0.7500 | 0.8333 | 0.0000 | 1.0000 | 0.6165 | 0.5988 | 0.9421 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `rag-core-components` | `general` | `all` | success | 3 | 0.987 |
| `stable-indexing` | `general` | `all` | success | 3 | 0.417 |
| `observability-request` | `general` | `all` | success | 3 | 0.299 |
| `metrics-listening` | `general` | `all` | success | 3 | 0.511 |
| `distance-direction` | `general` | `all` | success | 3 | 0.858 |
| `ollama-embedding` | `general` | `all` | success | 3 | 0.819 |
| `unrelated-stock` | `general` | `all` | success | 3 | 0.686 |
| `unrelated-recipe` | `general` | `all` | success | 3 | 0.353 |
