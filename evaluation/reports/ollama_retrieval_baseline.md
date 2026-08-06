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
| `dataset_sha256` | `"81741dfc4e4a59698b45ba2565558203aa0f7906c077f98749eb88ce512019a6"` |
| `documents_sha256` | `"645e477edbcd6086226621abb76ddfa147b44acf56c632edf39e89e8220298b3"` |

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
| `average_duration_ms` | 317.3545 |

## Cases

| Case | Status | Top-K | Duration (ms) |
|---|---|---:|---:|
| `rag-core-components` | success | 3 | 298.792 |
| `stable-indexing` | success | 3 | 302.279 |
| `observability-request` | success | 3 | 303.235 |
| `metrics-listening` | success | 3 | 340.791 |
| `distance-direction` | success | 3 | 301.145 |
| `ollama-embedding` | success | 3 | 309.280 |
| `unrelated-stock` | success | 3 | 336.507 |
| `unrelated-recipe` | success | 3 | 346.807 |
