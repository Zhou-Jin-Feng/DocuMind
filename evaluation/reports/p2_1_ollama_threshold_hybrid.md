# RAG Evaluation Report: ollama-hybrid-retrieval-baseline

- Cases: 35
- Default Top-K: 3

## Run Configuration

| Setting | Value |
|---|---|
| `document_count` | `11` |
| `chunk_count` | `11` |
| `embedding_provider` | `"ollama"` |
| `embedding_model` | `"qwen3-embedding"` |
| `embedding_dimension` | `4096` |
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
| `retrieval_mode` | `"hybrid"` |
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
| `average_duration_ms` | 189.7225 |
| `p50_duration_ms` | 129.8592 |
| `p95_duration_ms` | 166.9436 |
| `maximum_duration_ms` | 2172.8481 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `threshold_hard_negative` | 25 | N/A | N/A | N/A | 0.0000 | 1.0000 | 134.0541 | 130.0021 | 160.8140 |
| `threshold_positive` | 10 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 328.8937 | 126.4116 | 1255.5503 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `holdout` | 15 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 135.2118 | 130.0021 | 166.9436 |
| `validation` | 20 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 230.6056 | 129.3933 | 246.4393 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `threshold-val-positive-001` | `threshold_positive` | `validation` | success | 3 | 2172.848 |
| `threshold-val-positive-002` | `threshold_positive` | `validation` | success | 3 | 130.801 |
| `threshold-val-positive-003` | `threshold_positive` | `validation` | success | 3 | 121.971 |
| `threshold-val-positive-004` | `threshold_positive` | `validation` | success | 3 | 133.402 |
| `threshold-val-positive-005` | `threshold_positive` | `validation` | success | 3 | 113.947 |
| `threshold-val-negative-001` | `threshold_hard_negative` | `validation` | success | 3 | 129.859 |
| `threshold-val-negative-002` | `threshold_hard_negative` | `validation` | success | 3 | 133.461 |
| `threshold-val-negative-003` | `threshold_hard_negative` | `validation` | success | 3 | 126.703 |
| `threshold-val-negative-004` | `threshold_hard_negative` | `validation` | success | 3 | 145.049 |
| `threshold-val-negative-005` | `threshold_hard_negative` | `validation` | success | 3 | 134.227 |
| `threshold-val-negative-006` | `threshold_hard_negative` | `validation` | success | 3 | 128.927 |
| `threshold-val-negative-007` | `threshold_hard_negative` | `validation` | success | 3 | 141.665 |
| `threshold-val-negative-008` | `threshold_hard_negative` | `validation` | success | 3 | 122.462 |
| `threshold-val-negative-009` | `threshold_hard_negative` | `validation` | success | 3 | 142.102 |
| `threshold-val-negative-010` | `threshold_hard_negative` | `validation` | success | 3 | 127.064 |
| `threshold-val-negative-011` | `threshold_hard_negative` | `validation` | success | 3 | 119.754 |
| `threshold-val-negative-012` | `threshold_hard_negative` | `validation` | success | 3 | 136.318 |
| `threshold-val-negative-013` | `threshold_hard_negative` | `validation` | success | 3 | 116.282 |
| `threshold-val-negative-014` | `threshold_hard_negative` | `validation` | success | 3 | 123.294 |
| `threshold-val-negative-015` | `threshold_hard_negative` | `validation` | success | 3 | 111.974 |
| `threshold-holdout-positive-001` | `threshold_positive` | `holdout` | success | 3 | 134.409 |
| `threshold-holdout-positive-002` | `threshold_positive` | `holdout` | success | 3 | 125.358 |
| `threshold-holdout-positive-003` | `threshold_positive` | `holdout` | success | 3 | 118.417 |
| `threshold-holdout-positive-004` | `threshold_positive` | `holdout` | success | 3 | 110.318 |
| `threshold-holdout-positive-005` | `threshold_positive` | `holdout` | success | 3 | 127.466 |
| `threshold-holdout-negative-001` | `threshold_hard_negative` | `holdout` | success | 3 | 131.289 |
| `threshold-holdout-negative-002` | `threshold_hard_negative` | `holdout` | success | 3 | 128.900 |
| `threshold-holdout-negative-003` | `threshold_hard_negative` | `holdout` | success | 3 | 130.002 |
| `threshold-holdout-negative-004` | `threshold_hard_negative` | `holdout` | success | 3 | 145.451 |
| `threshold-holdout-negative-005` | `threshold_hard_negative` | `holdout` | success | 3 | 140.332 |
| `threshold-holdout-negative-006` | `threshold_hard_negative` | `holdout` | success | 3 | 146.278 |
| `threshold-holdout-negative-007` | `threshold_hard_negative` | `holdout` | success | 3 | 123.133 |
| `threshold-holdout-negative-008` | `threshold_hard_negative` | `holdout` | success | 3 | 129.610 |
| `threshold-holdout-negative-009` | `threshold_hard_negative` | `holdout` | success | 3 | 164.448 |
| `threshold-holdout-negative-010` | `threshold_hard_negative` | `holdout` | success | 3 | 172.766 |
