# RAG Evaluation Report: demo-golden-dataset

- Cases: 32
- Default Top-K: 3

## Run Configuration

| Setting | Value |
|---|---|
| `baseline_type` | `"deterministic-hybrid"` |
| `retrieval_mode` | `"hybrid"` |
| `document_count` | `9` |
| `embedding_provider` | `"evaluation-fake"` |
| `embedding_model` | `"sha256-token-hash-v1"` |
| `embedding_dimension` | `64` |
| `case_count` | `32` |
| `case_top_k_values` | `[3]` |
| `score_threshold` | `null` |
| `dataset_sha256` | `"014afc432bb3824a9afb7e361878adb5605dec7e35a2b2a409b777c13f07fb56"` |
| `documents_sha256` | `"552c4de4204bda67ebba4b865d64f6a9ff4862d9dcc745f95993a7342ee10c4d"` |

## Aggregate Metrics

| Metric | Value |
|---|---:|
| `recall_at_k` | 0.5556 |
| `precision_at_k` | 0.1852 |
| `mrr_at_k` | 0.4136 |
| `top_k_hit_rate` | 0.5556 |
| `correct_document_avg_rank` | 1.7333 |
| `no_answer_retrieval_accuracy` | 0.0000 |
| `refusal_accuracy` | 1.0000 |
| `keyword_coverage` | 1.0000 |
| `successful_case_rate` | 1.0000 |
| `average_duration_ms` | 1.1217 |

## Metrics By Category

| Category | Cases | Recall@K | MRR@K | Hit Rate | No-answer Accuracy | Success | Avg ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `exact_term` | 6 | 0.5000 | 0.2778 | 0.5000 | N/A | 1.0000 | 1.1033 |
| `hard_negative` | 5 | 0.6000 | 0.4667 | 0.6000 | N/A | 1.0000 | 1.0877 |
| `keyword_precision` | 6 | 0.6667 | 0.5556 | 0.6667 | N/A | 1.0000 | 1.1761 |
| `multi_hop` | 4 | 0.7500 | 0.7500 | 0.7500 | N/A | 1.0000 | 1.2161 |
| `no_answer` | 5 | N/A | N/A | N/A | 0.0000 | 1.0000 | 1.0713 |
| `semantic_paraphrase` | 6 | 0.3333 | 0.1389 | 0.3333 | N/A | 1.0000 | 1.0933 |

## Cases

| Case | Category | Status | Top-K | Duration (ms) |
|---|---|---|---:|---:|
| `exact-rf-001` | `exact_term` | success | 3 | 1.334 |
| `exact-rf-002` | `exact_term` | success | 3 | 1.146 |
| `exact-life-001` | `exact_term` | success | 3 | 1.142 |
| `exact-life-002` | `exact_term` | success | 3 | 1.167 |
| `exact-eval-001` | `exact_term` | success | 3 | 0.885 |
| `exact-embed-001` | `exact_term` | success | 3 | 0.947 |
| `semantic-rf-001` | `semantic_paraphrase` | success | 3 | 1.149 |
| `semantic-rf-002` | `semantic_paraphrase` | success | 3 | 1.288 |
| `semantic-life-001` | `semantic_paraphrase` | success | 3 | 0.972 |
| `semantic-life-002` | `semantic_paraphrase` | success | 3 | 1.124 |
| `semantic-eval-001` | `semantic_paraphrase` | success | 3 | 0.977 |
| `semantic-embed-001` | `semantic_paraphrase` | success | 3 | 1.050 |
| `keyword-config-001` | `keyword_precision` | success | 3 | 1.888 |
| `keyword-config-002` | `keyword_precision` | success | 3 | 1.219 |
| `keyword-config-003` | `keyword_precision` | success | 3 | 0.985 |
| `keyword-config-004` | `keyword_precision` | success | 3 | 0.966 |
| `keyword-config-005` | `keyword_precision` | success | 3 | 0.945 |
| `keyword-config-006` | `keyword_precision` | success | 3 | 1.054 |
| `hard-negative-001` | `hard_negative` | success | 3 | 1.228 |
| `hard-negative-002` | `hard_negative` | success | 3 | 0.938 |
| `hard-negative-003` | `hard_negative` | success | 3 | 0.989 |
| `hard-negative-004` | `hard_negative` | success | 3 | 1.177 |
| `hard-negative-005` | `hard_negative` | success | 3 | 1.107 |
| `multi-hop-001` | `multi_hop` | success | 3 | 1.457 |
| `multi-hop-002` | `multi_hop` | success | 3 | 1.032 |
| `multi-hop-003` | `multi_hop` | success | 3 | 1.063 |
| `multi-hop-004` | `multi_hop` | success | 3 | 1.312 |
| `no-answer-001` | `no_answer` | success | 3 | 1.059 |
| `no-answer-002` | `no_answer` | success | 3 | 1.119 |
| `no-answer-003` | `no_answer` | success | 3 | 1.226 |
| `no-answer-004` | `no_answer` | success | 3 | 1.039 |
| `no-answer-005` | `no_answer` | success | 3 | 0.913 |
