# RAG Evaluation Report: ollama-retrieval-baseline

- Cases: 20
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
| `case_count` | `20` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `null` |
| `lexical_score_threshold` | `null` |
| `dense_weight` | `1.0` |
| `lexical_weight` | `1.0` |
| `rrf_k` | `60` |
| `candidate_multiplier` | `5` |
| `retrieval_mode` | `"dense"` |
| `enhancement_mode` | `"baseline"` |
| `distance_metric` | `"L2"` |
| `evaluation_split` | `"validation"` |
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
| `average_duration_ms` | 448.3927 |
| `p50_duration_ms` | 346.6909 |
| `p95_duration_ms` | 499.6729 |
| `maximum_duration_ms` | 2366.7564 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `threshold_hard_negative` | 15 | N/A | N/A | N/A | 0.0000 | 1.0000 | 352.0798 | 349.2309 | 385.4276 |
| `threshold_positive` | 5 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 737.3315 | 333.4462 | 1961.6301 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `validation` | 20 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 448.3927 | 346.6909 | 499.6729 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `threshold-val-positive-001` | `threshold_positive` | `validation` | success | 3 | 2366.756 |
| `threshold-val-positive-002` | `threshold_positive` | `validation` | success | 3 | 333.446 |
| `threshold-val-positive-003` | `threshold_positive` | `validation` | success | 3 | 331.116 |
| `threshold-val-positive-004` | `threshold_positive` | `validation` | success | 3 | 314.215 |
| `threshold-val-positive-005` | `threshold_positive` | `validation` | success | 3 | 341.125 |
| `threshold-val-negative-001` | `threshold_hard_negative` | `validation` | success | 3 | 330.991 |
| `threshold-val-negative-002` | `threshold_hard_negative` | `validation` | success | 3 | 335.275 |
| `threshold-val-negative-003` | `threshold_hard_negative` | `validation` | success | 3 | 346.629 |
| `threshold-val-negative-004` | `threshold_hard_negative` | `validation` | success | 3 | 360.947 |
| `threshold-val-negative-005` | `threshold_hard_negative` | `validation` | success | 3 | 335.563 |
| `threshold-val-negative-006` | `threshold_hard_negative` | `validation` | success | 3 | 339.080 |
| `threshold-val-negative-007` | `threshold_hard_negative` | `validation` | success | 3 | 357.608 |
| `threshold-val-negative-008` | `threshold_hard_negative` | `validation` | success | 3 | 325.277 |
| `threshold-val-negative-009` | `threshold_hard_negative` | `validation` | success | 3 | 370.019 |
| `threshold-val-negative-010` | `threshold_hard_negative` | `validation` | success | 3 | 378.580 |
| `threshold-val-negative-011` | `threshold_hard_negative` | `validation` | success | 3 | 346.753 |
| `threshold-val-negative-012` | `threshold_hard_negative` | `validation` | success | 3 | 353.577 |
| `threshold-val-negative-013` | `threshold_hard_negative` | `validation` | success | 3 | 401.405 |
| `threshold-val-negative-014` | `threshold_hard_negative` | `validation` | success | 3 | 350.261 |
| `threshold-val-negative-015` | `threshold_hard_negative` | `validation` | success | 3 | 349.231 |
