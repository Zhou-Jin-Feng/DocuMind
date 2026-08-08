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
| `enhancement_mode` | `"baseline"` |
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
| `dataset_path` | `"evaluation/datasets/v1_6/holdout_dataset.jsonl"` |
| `documents_directory` | `"evaluation/datasets/v1_6/documents"` |
| `dataset_sha256` | `"82e5e1cefcb230eea220ff6bd26c90e087d7f8fe36c7b5a18d5c729693273eba"` |
| `documents_sha256` | `"552c4de4204bda67ebba4b865d64f6a9ff4862d9dcc745f95993a7342ee10c4d"` |

## Aggregate Metrics

| Metric | Value |
|---|---:|
| `recall_at_k` | 1.0000 |
| `precision_at_k` | 0.3333 |
| `mrr_at_k` | 0.9545 |
| `top_k_hit_rate` | 1.0000 |
| `correct_document_avg_rank` | 1.0909 |
| `no_answer_retrieval_accuracy` | 1.0000 |
| `refusal_accuracy` | N/A |
| `keyword_coverage` | N/A |
| `successful_case_rate` | 1.0000 |
| `average_duration_ms` | 308.3465 |
| `p50_duration_ms` | 308.6717 |
| `p95_duration_ms` | 325.7434 |
| `maximum_duration_ms` | 326.6872 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `exact_term` | 3 | 1.0000 | 0.8333 | 1.0000 | N/A | 1.0000 | 305.4407 | 316.5117 | 318.6994 |
| `hard_negative` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 314.6236 | 314.6236 | 323.9364 |
| `no_answer` | 1 | N/A | N/A | N/A | 1.0000 | 1.0000 | 301.2625 | 301.2625 | 301.2625 |
| `observability` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 326.6872 | 326.6872 | 326.6872 |
| `quality_gate` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 323.7402 | 323.7402 | 323.7402 |
| `retrieval_quality` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 300.0951 | 300.0951 | 307.2979 |
| `security` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 301.3542 | 301.3542 | 308.4561 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `holdout` | 12 | 1.0000 | 0.9545 | 1.0000 | 1.0000 | 1.0000 | 308.3465 | 308.6717 | 325.7434 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `holdout-life-001` | `exact_term` | `holdout` | success | 3 | 280.868 |
| `holdout-life-002` | `hard_negative` | `holdout` | success | 3 | 304.276 |
| `holdout-embed-001` | `exact_term` | `holdout` | success | 3 | 318.943 |
| `holdout-embed-002` | `hard_negative` | `holdout` | success | 3 | 324.971 |
| `holdout-eval-001` | `exact_term` | `holdout` | success | 3 | 316.512 |
| `holdout-eval-002` | `quality_gate` | `holdout` | success | 3 | 323.740 |
| `holdout-observe-001` | `observability` | `holdout` | success | 3 | 326.687 |
| `holdout-observe-002` | `security` | `holdout` | success | 3 | 309.245 |
| `holdout-security-001` | `security` | `holdout` | success | 3 | 293.463 |
| `holdout-retrieval-001` | `retrieval_quality` | `holdout` | success | 3 | 292.092 |
| `holdout-troubleshoot-001` | `retrieval_quality` | `holdout` | success | 3 | 308.098 |
| `holdout-no-answer-001` | `no_answer` | `holdout` | success | 3 | 301.262 |
