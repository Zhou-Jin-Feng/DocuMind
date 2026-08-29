# Retrieve Quality Report: documind-retrieve-quality-v1

> Scope: offline deterministic Dense regression. This report does not measure a production Embedding or Milvus deployment.

## Metrics

| Metric | Value |
|---|---:|
| `recall_at_k` | 1.000000 |
| `precision_at_k` | 0.500000 |
| `mrr_at_k` | 1.000000 |
| `ndcg_at_k` | 1.000000 |
| `no_answer_empty_accuracy` | 1.000000 |
| `api_bottom_parity_rate` | 1.000000 |
| `contamination_free_rate` | 1.000000 |
| `empty_result_rate` | 0.200000 |
| `successful_case_rate` | 1.000000 |

## Reproduction Metadata

| Setting | Value |
|---|---|
| `evaluation_scope` | `"offline-deterministic-dense"` |
| `production_provider_conclusion` | `false` |
| `dataset_version` | `"1.0"` |
| `dataset_sha256` | `"0a3b71a25f7aefd73df006d622d5b404ca418e9a1672f4272167c4ee430f26e2"` |
| `documents_sha256` | `"f83815e7cceb4ed135e19d263916bfc1a8bb18536ecd2e98a8165c8306efca8a"` |
| `document_count` | `2` |
| `chunk_count` | `6` |
| `case_top_k_values` | `[2]` |
| `retrieval_mode` | `"dense"` |
| `score_threshold` | `"per-case"` |
| `embedding_provider` | `"evaluation-fake"` |
| `embedding_model` | `"sha256-token-hash-v1"` |
| `embedding_dimension` | `64` |
| `chunk_size` | `null` |
| `chunk_overlap` | `null` |
| `schema_version` | `"1.0"` |
| `retrieval_version` | `"dense-v1"` |
| `service_version` | `"2.1.0"` |
| `python_version` | `"3.14.6"` |
| `python_implementation` | `"CPython"` |
| `platform` | `"windows"` |

## Cases

| Case | Retrieved | Recall | MRR | nDCG | Parity | Contamination |
|---|---|---:|---:|---:|---:|---:|
| `dense-source-evidence` | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 |
| `active-index-isolation` | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 |
| `evidence-integrity` | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 |
| `graph-community-scope` | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 |
| `bounded-empty-result` | 0 | null | null | null | 1.0000 | 0 |
