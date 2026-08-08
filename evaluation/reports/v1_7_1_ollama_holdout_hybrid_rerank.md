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
| `enhancement_mode` | `"rerank"` |
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
| `average_duration_ms` | 1018.8614 |
| `p50_duration_ms` | 690.0130 |
| `p95_duration_ms` | 2461.9963 |
| `maximum_duration_ms` | 3789.3799 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `exact_term` | 3 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 1710.8234 | 836.7940 | 3494.1213 |
| `hard_negative` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 623.7035 | 623.7035 | 648.3862 |
| `no_answer` | 1 | N/A | N/A | N/A | 1.0000 | 1.0000 | 319.5978 | 319.5978 | 319.5978 |
| `observability` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 495.7858 | 495.7858 | 495.7858 |
| `quality_gate` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 728.8974 | 728.8974 | 728.8974 |
| `retrieval_quality` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 1207.0508 | 1207.0508 | 1316.8235 |
| `security` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 944.0386 | 944.0386 | 1332.7635 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `holdout` | 12 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1018.8614 | 690.0130 | 2461.9963 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `holdout-life-001` | `exact_term` | `holdout` | success | 3 | 3789.380 |
| `holdout-life-002` | `hard_negative` | `holdout` | success | 3 | 596.278 |
| `holdout-embed-001` | `exact_term` | `holdout` | success | 3 | 506.296 |
| `holdout-embed-002` | `hard_negative` | `holdout` | success | 3 | 651.129 |
| `holdout-eval-001` | `exact_term` | `holdout` | success | 3 | 836.794 |
| `holdout-eval-002` | `quality_gate` | `holdout` | success | 3 | 728.897 |
| `holdout-observe-001` | `observability` | `holdout` | success | 3 | 495.786 |
| `holdout-observe-002` | `security` | `holdout` | success | 3 | 1375.955 |
| `holdout-security-001` | `security` | `holdout` | success | 3 | 512.122 |
| `holdout-retrieval-001` | `retrieval_quality` | `holdout` | success | 3 | 1085.081 |
| `holdout-troubleshoot-001` | `retrieval_quality` | `holdout` | success | 3 | 1329.021 |
| `holdout-no-answer-001` | `no_answer` | `holdout` | success | 3 | 319.598 |
