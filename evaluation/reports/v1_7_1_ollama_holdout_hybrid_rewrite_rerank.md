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
| `enhancement_mode` | `"rewrite-rerank"` |
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
| `average_duration_ms` | 1742.6193 |
| `p50_duration_ms` | 1674.4020 |
| `p95_duration_ms` | 2608.7051 |
| `maximum_duration_ms` | 3059.9419 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `exact_term` | 3 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 2157.3947 | 1855.8191 | 2939.5296 |
| `hard_negative` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 1496.7926 | 1496.7926 | 1727.0588 |
| `no_answer` | 1 | N/A | N/A | N/A | 1.0000 | 1.0000 | 1006.6583 | 1006.6583 | 1006.6583 |
| `observability` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 1208.7178 | 1208.7178 | 1208.7178 |
| `quality_gate` | 1 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 1989.9966 | 1989.9966 | 1989.9966 |
| `retrieval_quality` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 1917.8358 | 1917.8358 | 2207.3438 |
| `security` | 2 | 1.0000 | 1.0000 | 1.0000 | N/A | 1.0000 | 1702.3093 | 1702.3093 | 2135.6096 |

## Metrics By Split

| Split | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `holdout` | 12 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1742.6193 | 1674.4020 | 2608.7051 |

## Cases

| Case | Category | Split | Status | Top-K | Duration (ms) |
|---|---|---|---|---:|---:|
| `holdout-life-001` | `exact_term` | `holdout` | success | 3 | 3059.942 |
| `holdout-life-002` | `hard_negative` | `holdout` | success | 3 | 1240.941 |
| `holdout-embed-001` | `exact_term` | `holdout` | success | 3 | 1855.819 |
| `holdout-embed-002` | `hard_negative` | `holdout` | success | 3 | 1752.644 |
| `holdout-eval-001` | `exact_term` | `holdout` | success | 3 | 1556.423 |
| `holdout-eval-002` | `quality_gate` | `holdout` | success | 3 | 1989.997 |
| `holdout-observe-001` | `observability` | `holdout` | success | 3 | 1208.718 |
| `holdout-observe-002` | `security` | `holdout` | success | 3 | 2183.754 |
| `holdout-security-001` | `security` | `holdout` | success | 3 | 1220.864 |
| `holdout-retrieval-001` | `retrieval_quality` | `holdout` | success | 3 | 1596.160 |
| `holdout-troubleshoot-001` | `retrieval_quality` | `holdout` | success | 3 | 2239.511 |
| `holdout-no-answer-001` | `no_answer` | `holdout` | success | 3 | 1006.658 |
