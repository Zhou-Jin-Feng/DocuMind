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
| `enhancement_mode` | `"rerank"` |
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
| `reranker_model` | `"BAAI/bge-reranker-base"` |
| `sentence_transformers_version` | `"5.7.0"` |
| `reranker_batch_size` | `8` |
| `reranker_device` | `"cpu"` |
| `reranker_local_files_only` | `true` |
| `rerank_candidate_multiplier` | `5` |
| `dataset_path` | `"evaluation/datasets/v2_answer_quality/threshold_dataset.jsonl"` |
| `documents_directory` | `"evaluation/datasets/v2_answer_quality/documents"` |
| `dataset_sha256` | `"8853bf2aba5bc1266bd7202b6f7feb084a0fca242d475d6c2204928fdab12210"` |
| `documents_sha256` | `"7655501aca56852fd4db7755b8fea6512705b837cd070d5e9e00ad373a878103"` |

## Aggregate Metrics

| Metric | Value |
|---|---:|
| `recall_at_k` | 1.0000 |
| `precision_at_k` | 0.3333 |
| `mrr_at_k` | 0.9500 |
| `top_k_hit_rate` | 1.0000 |
| `correct_document_avg_rank` | 1.1000 |
| `no_answer_retrieval_accuracy` | 0.0000 |
| `refusal_accuracy` | N/A |
| `keyword_coverage` | N/A |
| `successful_case_rate` | 1.0000 |
| `average_duration_ms` | 1896.7678 |
| `p50_duration_ms` | 1631.0015 |
| `p95_duration_ms` | 2849.0104 |
| `maximum_duration_ms` | 7360.4331 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `threshold_hard_negative` | 25 | N/A | N/A | N/A | 0.0000 | 1.0000 | 1711.1499 | 1640.1119 | 2065.8412 |
| `threshold_positive` | 10 | 1.0000 | 0.9500 | 1.0000 | N/A | 1.0000 | 2360.8125 | 1601.9936 | 5661.3249 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `holdout` | 15 | 1.0000 | 0.9000 | 1.0000 | 0.0000 | 1.0000 | 1753.6088 | 1640.1119 | 2237.6186 |
| `validation` | 20 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 2004.1370 | 1599.1661 | 3773.4269 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `threshold-val-positive-001` | `threshold_positive` | `validation` | success | 3 | 7360.433 |
| `threshold-val-positive-002` | `threshold_positive` | `validation` | success | 3 | 3584.637 |
| `threshold-val-positive-003` | `threshold_positive` | `validation` | success | 3 | 1513.218 |
| `threshold-val-positive-004` | `threshold_positive` | `validation` | success | 3 | 1540.663 |
| `threshold-val-positive-005` | `threshold_positive` | `validation` | success | 3 | 1480.714 |
| `threshold-val-negative-001` | `threshold_hard_negative` | `validation` | success | 3 | 1570.557 |
| `threshold-val-negative-002` | `threshold_hard_negative` | `validation` | success | 3 | 1566.473 |
| `threshold-val-negative-003` | `threshold_hard_negative` | `validation` | success | 3 | 1499.184 |
| `threshold-val-negative-004` | `threshold_hard_negative` | `validation` | success | 3 | 1594.390 |
| `threshold-val-negative-005` | `threshold_hard_negative` | `validation` | success | 3 | 1509.914 |
| `threshold-val-negative-006` | `threshold_hard_negative` | `validation` | success | 3 | 1863.413 |
| `threshold-val-negative-007` | `threshold_hard_negative` | `validation` | success | 3 | 1873.268 |
| `threshold-val-negative-008` | `threshold_hard_negative` | `validation` | success | 3 | 1603.942 |
| `threshold-val-negative-009` | `threshold_hard_negative` | `validation` | success | 3 | 1772.680 |
| `threshold-val-negative-010` | `threshold_hard_negative` | `validation` | success | 3 | 1641.033 |
| `threshold-val-negative-011` | `threshold_hard_negative` | `validation` | success | 3 | 1731.509 |
| `threshold-val-negative-012` | `threshold_hard_negative` | `validation` | success | 3 | 1666.569 |
| `threshold-val-negative-013` | `threshold_hard_negative` | `validation` | success | 3 | 1671.373 |
| `threshold-val-negative-014` | `threshold_hard_negative` | `validation` | success | 3 | 1536.354 |
| `threshold-val-negative-015` | `threshold_hard_negative` | `validation` | success | 3 | 1502.415 |
| `threshold-holdout-positive-001` | `threshold_positive` | `holdout` | success | 3 | 1720.859 |
| `threshold-holdout-positive-002` | `threshold_positive` | `holdout` | success | 3 | 1631.002 |
| `threshold-holdout-positive-003` | `threshold_positive` | `holdout` | success | 3 | 1557.799 |
| `threshold-holdout-positive-004` | `threshold_positive` | `holdout` | success | 3 | 1572.986 |
| `threshold-holdout-positive-005` | `threshold_positive` | `holdout` | success | 3 | 1645.816 |
| `threshold-holdout-negative-001` | `threshold_hard_negative` | `holdout` | success | 3 | 1556.137 |
| `threshold-holdout-negative-002` | `threshold_hard_negative` | `holdout` | success | 3 | 1588.122 |
| `threshold-holdout-negative-003` | `threshold_hard_negative` | `holdout` | success | 3 | 1621.081 |
| `threshold-holdout-negative-004` | `threshold_hard_negative` | `holdout` | success | 3 | 1613.600 |
| `threshold-holdout-negative-005` | `threshold_hard_negative` | `holdout` | success | 3 | 2110.709 |
| `threshold-holdout-negative-006` | `threshold_hard_negative` | `holdout` | success | 3 | 2533.742 |
| `threshold-holdout-negative-007` | `threshold_hard_negative` | `holdout` | success | 3 | 1793.163 |
| `threshold-holdout-negative-008` | `threshold_hard_negative` | `holdout` | success | 3 | 1640.112 |
| `threshold-holdout-negative-009` | `threshold_hard_negative` | `holdout` | success | 3 | 1886.372 |
| `threshold-holdout-negative-010` | `threshold_hard_negative` | `holdout` | success | 3 | 1832.635 |
