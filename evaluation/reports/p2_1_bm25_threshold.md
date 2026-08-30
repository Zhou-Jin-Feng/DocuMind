# RAG Evaluation Report: ollama-bm25-retrieval-baseline

- Cases: 35
- Default Top-K: 3

## Run Configuration

| Setting | Value |
|---|---|
| `document_count` | `11` |
| `chunk_count` | `11` |
| `embedding_provider` | `"none"` |
| `embedding_model` | `"none"` |
| `embedding_dimension` | `0` |
| `chunk_size` | `500` |
| `chunk_overlap` | `100` |
| `case_count` | `35` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `null` |
| `lexical_score_threshold` | `null` |
| `dense_weight` | `1.0` |
| `lexical_weight` | `1.0` |
| `rrf_k` | `60` |
| `candidate_multiplier` | `5` |
| `retrieval_mode` | `"bm25"` |
| `enhancement_mode` | `"baseline"` |
| `distance_metric` | `null` |
| `evaluation_split` | `"all"` |
| `rewrite_provider` | `null` |
| `rewrite_model` | `null` |
| `rewrite_map_path` | `null` |
| `rewrite_map_sha256` | `null` |
| `rewrite_artifact_version` | `null` |
| `rewrite_artifact_max_rewrites` | `null` |
| `rewrite_generation_max_tokens` | `null` |
| `rewrite_temperature` | `null` |
| `rewrite_prompt_sha256` | `null` |
| `max_rewrites` | `null` |
| `rewrite_max_tokens` | `null` |
| `query_rrf_k` | `null` |
| `per_query_candidate_multiplier` | `null` |
| `reranker_model` | `null` |
| `sentence_transformers_version` | `null` |
| `reranker_batch_size` | `null` |
| `reranker_device` | `null` |
| `reranker_local_files_only` | `null` |
| `rerank_candidate_multiplier` | `null` |
| `dataset_path` | `"evaluation/datasets/v2_answer_quality/threshold_dataset.jsonl"` |
| `documents_directory` | `"evaluation/datasets/v2_answer_quality/documents"` |
| `dataset_sha256` | `"8853bf2aba5bc1266bd7202b6f7feb084a0fca242d475d6c2204928fdab12210"` |
| `documents_sha256` | `"7655501aca56852fd4db7755b8fea6512705b837cd070d5e9e00ad373a878103"` |

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
| `average_duration_ms` | 0.4696 |
| `p50_duration_ms` | 0.4229 |
| `p95_duration_ms` | 0.6028 |
| `maximum_duration_ms` | 2.0482 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `threshold_hard_negative` | 25 | N/A | N/A | N/A | 0.0000 | 1.0000 | 0.4875 | 0.4284 | 0.5966 |
| `threshold_positive` | 10 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 0.4248 | 0.4064 | 0.5944 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `holdout` | 15 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.4633 | 0.4551 | 0.5842 |
| `validation` | 20 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.4743 | 0.3739 | 0.6742 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `threshold-val-positive-001` | `threshold_positive` | `validation` | success | 3 | 0.581 |
| `threshold-val-positive-002` | `threshold_positive` | `validation` | success | 3 | 0.312 |
| `threshold-val-positive-003` | `threshold_positive` | `validation` | success | 3 | 0.397 |
| `threshold-val-positive-004` | `threshold_positive` | `validation` | success | 3 | 0.416 |
| `threshold-val-positive-005` | `threshold_positive` | `validation` | success | 3 | 0.259 |
| `threshold-val-negative-001` | `threshold_hard_negative` | `validation` | success | 3 | 0.323 |
| `threshold-val-negative-002` | `threshold_hard_negative` | `validation` | success | 3 | 2.048 |
| `threshold-val-negative-003` | `threshold_hard_negative` | `validation` | success | 3 | 0.602 |
| `threshold-val-negative-004` | `threshold_hard_negative` | `validation` | success | 3 | 0.433 |
| `threshold-val-negative-005` | `threshold_hard_negative` | `validation` | success | 3 | 0.423 |
| `threshold-val-negative-006` | `threshold_hard_negative` | `validation` | success | 3 | 0.315 |
| `threshold-val-negative-007` | `threshold_hard_negative` | `validation` | success | 3 | 0.349 |
| `threshold-val-negative-008` | `threshold_hard_negative` | `validation` | success | 3 | 0.383 |
| `threshold-val-negative-009` | `threshold_hard_negative` | `validation` | success | 3 | 0.539 |
| `threshold-val-negative-010` | `threshold_hard_negative` | `validation` | success | 3 | 0.320 |
| `threshold-val-negative-011` | `threshold_hard_negative` | `validation` | success | 3 | 0.467 |
| `threshold-val-negative-012` | `threshold_hard_negative` | `validation` | success | 3 | 0.364 |
| `threshold-val-negative-013` | `threshold_hard_negative` | `validation` | success | 3 | 0.353 |
| `threshold-val-negative-014` | `threshold_hard_negative` | `validation` | success | 3 | 0.336 |
| `threshold-val-negative-015` | `threshold_hard_negative` | `validation` | success | 3 | 0.265 |
| `threshold-holdout-positive-001` | `threshold_positive` | `holdout` | success | 3 | 0.460 |
| `threshold-holdout-positive-002` | `threshold_positive` | `holdout` | success | 3 | 0.372 |
| `threshold-holdout-positive-003` | `threshold_positive` | `holdout` | success | 3 | 0.339 |
| `threshold-holdout-positive-004` | `threshold_positive` | `holdout` | success | 3 | 0.509 |
| `threshold-holdout-positive-005` | `threshold_positive` | `holdout` | success | 3 | 0.605 |
| `threshold-holdout-negative-001` | `threshold_hard_negative` | `holdout` | success | 3 | 0.398 |
| `threshold-holdout-negative-002` | `threshold_hard_negative` | `holdout` | success | 3 | 0.554 |
| `threshold-holdout-negative-003` | `threshold_hard_negative` | `holdout` | success | 3 | 0.428 |
| `threshold-holdout-negative-004` | `threshold_hard_negative` | `holdout` | success | 3 | 0.443 |
| `threshold-holdout-negative-005` | `threshold_hard_negative` | `holdout` | success | 3 | 0.532 |
| `threshold-holdout-negative-006` | `threshold_hard_negative` | `holdout` | success | 3 | 0.518 |
| `threshold-holdout-negative-007` | `threshold_hard_negative` | `holdout` | success | 3 | 0.435 |
| `threshold-holdout-negative-008` | `threshold_hard_negative` | `holdout` | success | 3 | 0.328 |
| `threshold-holdout-negative-009` | `threshold_hard_negative` | `holdout` | success | 3 | 0.575 |
| `threshold-holdout-negative-010` | `threshold_hard_negative` | `holdout` | success | 3 | 0.455 |
