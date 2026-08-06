# RAG Evaluation Report: demo-golden-dataset

- Cases: 8
- Default Top-K: 3

## Run Configuration

| Setting | Value |
|---|---|
| `baseline_type` | `"deterministic-smoke"` |
| `document_count` | `5` |
| `embedding_provider` | `"evaluation-fake"` |
| `embedding_model` | `"sha256-token-hash-v1"` |
| `embedding_dimension` | `64` |
| `case_count` | `8` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `null` |
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
| `average_duration_ms` | 0.7156 |

## Cases

| Case | Status | Top-K | Duration (ms) |
|---|---|---:|---:|
| `rag-core-components` | success | 3 | 0.986 |
| `stable-indexing` | success | 3 | 0.715 |
| `observability-request` | success | 3 | 0.632 |
| `metrics-listening` | success | 3 | 0.729 |
| `distance-direction` | success | 3 | 0.642 |
| `ollama-embedding` | success | 3 | 0.639 |
| `unrelated-stock` | success | 3 | 0.608 |
| `unrelated-recipe` | success | 3 | 0.772 |
