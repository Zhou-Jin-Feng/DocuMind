# v1.7.1 Retrieval Enhancement Comparison

## Common Configuration

| Setting | Value |
|---|---|
| `embedding_provider` | `"ollama"` |
| `embedding_model` | `"qwen3-embedding"` |
| `embedding_dimension` | `4096` |
| `chunk_size` | `500` |
| `chunk_overlap` | `100` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `1.0` |
| `lexical_score_threshold` | `12.2` |
| `dense_weight` | `1.0` |
| `lexical_weight` | `1.0` |
| `rrf_k` | `60` |
| `candidate_multiplier` | `5` |
| `retrieval_mode` | `"hybrid"` |
| `dataset_sha256` | `"82e5e1cefcb230eea220ff6bd26c90e087d7f8fe36c7b5a18d5c729693273eba"` |
| `documents_sha256` | `"552c4de4204bda67ebba4b865d64f6a9ff4862d9dcc745f95993a7342ee10c4d"` |

## Quality And Latency

| Mode | Recall@K | Precision@K | MRR@K | Hit Rate | No-answer | Success | Avg ms | P50 ms | P95 ms | Max ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline` | 1.0000 | 0.3333 | 0.9545 | 1.0000 | 1.0000 | 1.0000 | 308.3465 | 308.6717 | 325.7434 | 326.6872 |
| `rewrite` | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 890.2286 | 878.5421 | 961.3560 | 969.7705 |
| `rerank` | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1018.8614 | 690.0130 | 2461.9963 | 3789.3799 |
| `rewrite-rerank` | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1742.6193 | 1674.4020 | 2608.7051 | 3059.9419 |

All deltas in the JSON artifact use `mode - baseline`; quality and latency are intentionally not collapsed into one score.
