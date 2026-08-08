# RAG Evaluation Report: ollama-hybrid-retrieval-baseline

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
| `score_threshold` | `1.0` |
| `lexical_score_threshold` | `12.2` |
| `dense_weight` | `1.0` |
| `lexical_weight` | `1.0` |
| `rrf_k` | `60` |
| `candidate_multiplier` | `5` |
| `retrieval_mode` | `"hybrid"` |
| `enhancement_mode` | `"rewrite"` |
| `rewrite_provider` | `"deepseek"` |
| `rewrite_model` | `"deepseek-chat"` |
| `rewrite_map_path` | `"evaluation/datasets/v1_7/holdout_rewrites_deepseek.json"` |
| `rewrite_map_sha256` | `"9e38c2edb985d8d17e7b34daf84f000cfb271de72f70a92c0c9e66448ed278de"` |
| `rewrite_artifact_version` | `1` |
| `rewrite_artifact_max_rewrites` | `2` |
| `rewrite_generation_max_tokens` | `256` |
| `rewrite_temperature` | `0.0` |
| `rewrite_prompt_sha256` | `"ccde1ce70a897317ed01bd1492637ad41a1527b2f8d7abd174ade75b74a0f24b"` |
| `max_rewrites` | `2` |
| `rewrite_max_tokens` | `null` |
| `query_rrf_k` | `60` |
| `per_query_candidate_multiplier` | `1` |
| `reranker_model` | `null` |
| `sentence_transformers_version` | `null` |
| `reranker_batch_size` | `null` |
| `reranker_device` | `null` |
| `reranker_local_files_only` | `null` |
| `rerank_candidate_multiplier` | `null` |
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
| `no_answer_retrieval_accuracy` | 1.0000 |
| `refusal_accuracy` | N/A |
| `keyword_coverage` | N/A |
| `successful_case_rate` | 1.0000 |
| `average_duration_ms` | 890.2286 |
| `p50_duration_ms` | 878.5421 |
| `p95_duration_ms` | 961.3560 |
| `maximum_duration_ms` | 969.7705 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `exact_term` | 3 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 867.9057 | 862.0944 | 945.2337 |
| `hard_negative` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 892.6231 | 892.6231 | 933.0516 |
| `no_answer` | 1 | N/A | N/A | N/A | 1.0000 | 1.0000 | 878.2078 | 878.2078 | 878.2078 |
| `observability` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 864.4961 | 864.4961 | 864.4961 |
| `quality_gate` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 928.4156 | 928.4156 | 928.4156 |
| `retrieval_quality` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 887.0066 | 887.0066 | 896.2198 |
| `security` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 924.3235 | 924.3235 | 965.2258 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `holdout` | 12 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 890.2286 | 878.5421 | 961.3560 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `holdout-life-001` | `exact_term` | `holdout` | success | 3 | 787.151 |
| `holdout-life-002` | `hard_negative` | `holdout` | success | 3 | 847.703 |
| `holdout-embed-001` | `exact_term` | `holdout` | success | 3 | 954.471 |
| `holdout-embed-002` | `hard_negative` | `holdout` | success | 3 | 937.544 |
| `holdout-eval-001` | `exact_term` | `holdout` | success | 3 | 862.094 |
| `holdout-eval-002` | `quality_gate` | `holdout` | success | 3 | 928.416 |
| `holdout-observe-001` | `observability` | `holdout` | success | 3 | 864.496 |
| `holdout-observe-002` | `security` | `holdout` | success | 3 | 878.876 |
| `holdout-security-001` | `security` | `holdout` | success | 3 | 969.770 |
| `holdout-retrieval-001` | `retrieval_quality` | `holdout` | success | 3 | 876.770 |
| `holdout-troubleshoot-001` | `retrieval_quality` | `holdout` | success | 3 | 897.244 |
| `holdout-no-answer-001` | `no_answer` | `holdout` | success | 3 | 878.208 |
