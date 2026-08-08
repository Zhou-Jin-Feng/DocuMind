# RAG Evaluation Report: ollama-retrieval-baseline

- Cases: 12
- Default Top-K: 3

## Run Configuration

| Setting | Value |
|---|---|
| `document_count` | `9` |
| `chunk_count` | `10` |
| `embedding_provider` | `"ollama"` |
| `embedding_model` | `"qwen3-embedding"` |
| `embedding_dimension` | `4096` |
| `chunk_size` | `500` |
| `chunk_overlap` | `100` |
| `case_count` | `12` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `null` |
| `lexical_score_threshold` | `null` |
| `dense_weight` | `1.0` |
| `lexical_weight` | `1.0` |
| `rrf_k` | `60` |
| `candidate_multiplier` | `5` |
| `retrieval_mode` | `"dense"` |
| `dataset_path` | `"evaluation/datasets/v1_6/holdout_dataset.jsonl"` |
| `documents_directory` | `"evaluation/datasets/v1_6/documents"` |
| `dataset_sha256` | `"82e5e1cefcb230eea220ff6bd26c90e087d7f8fe36c7b5a18d5c729693273eba"` |
| `documents_sha256` | `"552c4de4204bda67ebba4b865d64f6a9ff4862d9dcc745f95993a7342ee10c4d"` |

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
| `average_duration_ms` | 329.2278 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `exact_term` | 3 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 304.2328 |
| `hard_negative` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 313.0029 |
| `no_answer` | 1 | N/A | N/A | N/A | 0.0000 | 1.0000 | 312.9856 |
| `observability` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 368.3397 |
| `quality_gate` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 349.8233 |
| `retrieval_quality` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 333.9638 |
| `security` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 356.4765 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `holdout` | 12 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 329.2278 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `holdout-life-001` | `exact_term` | `holdout` | success | 3 | 297.921 |
| `holdout-life-002` | `hard_negative` | `holdout` | success | 3 | 293.056 |
| `holdout-embed-001` | `exact_term` | `holdout` | success | 3 | 299.315 |
| `holdout-embed-002` | `hard_negative` | `holdout` | success | 3 | 332.949 |
| `holdout-eval-001` | `exact_term` | `holdout` | success | 3 | 315.462 |
| `holdout-eval-002` | `quality_gate` | `holdout` | success | 3 | 349.823 |
| `holdout-observe-001` | `observability` | `holdout` | success | 3 | 368.340 |
| `holdout-observe-002` | `security` | `holdout` | success | 3 | 364.818 |
| `holdout-security-001` | `security` | `holdout` | success | 3 | 348.135 |
| `holdout-retrieval-001` | `retrieval_quality` | `holdout` | success | 3 | 342.855 |
| `holdout-troubleshoot-001` | `retrieval_quality` | `holdout` | success | 3 | 325.072 |
| `holdout-no-answer-001` | `no_answer` | `holdout` | success | 3 | 312.986 |
