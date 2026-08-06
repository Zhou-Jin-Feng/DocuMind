# RAG Evaluation Report: ollama-retrieval-baseline

- Cases: 8
- Default Top-K: 3

## Run Configuration

| Setting | Value |
|---|---|
| `document_count` | `5` |
| `chunk_count` | `5` |
| `embedding_provider` | `"ollama"` |
| `embedding_model` | `"qwen3-embedding"` |
| `embedding_dimension` | `4096` |
| `chunk_size` | `500` |
| `chunk_overlap` | `100` |
| `case_count` | `8` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `null` |
| `dataset_path` | `"evaluation/datasets/golden_dataset.jsonl"` |
| `documents_directory` | `"evaluation/datasets/documents"` |

## Aggregate Metrics

| Metric | Value |
|---|---:|
| `recall_at_k` | 1.0000 |
| `precision_at_k` | 0.3333 |
| `mrr_at_k` | 1.0000 |
| `top_k_hit_rate` | 1.0000 |
| `correct_document_avg_rank` | 1.0000 |
| `no_answer_retrieval_accuracy` | 0.0000 |
| `refusal_accuracy` | N/A |
| `keyword_coverage` | N/A |
| `successful_case_rate` | 1.0000 |
| `average_duration_ms` | 345.1527 |

## Cases

| Case | Status | Top-K | Duration (ms) |
|---|---|---:|---:|
| `rag-core-components` | success | 3 | 419.668 |
| `stable-indexing` | success | 3 | 363.559 |
| `observability-request` | success | 3 | 337.272 |
| `metrics-listening` | success | 3 | 378.865 |
| `distance-direction` | success | 3 | 329.169 |
| `ollama-embedding` | success | 3 | 327.989 |
| `unrelated-stock` | success | 3 | 308.394 |
| `unrelated-recipe` | success | 3 | 296.306 |
