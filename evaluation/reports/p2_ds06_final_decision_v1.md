# DS-06 Retrieval Evaluation Decision

Decision: **NO_GO**

Selected candidate: `none`

Selected Reranker depth (validation only): `5`

## Holdout Comparison

| Mode | Eligible | Recall@3 | MRR@3 | nDCG@3 | P95 ms | Failures |
|---|---|---:|---:|---:|---:|---:|
| `dense` | yes | 0.4054 | 0.3018 | 0.3278 | 170.2527 | 0 |
| `bm25` | no | 0.3243 | 0.2477 | 0.2564 | 7.9377 | 4 |
| `hybrid` | no | 0.3919 | 0.3153 | 0.3234 | 186.7921 | 2 |
| `rerank` | no | 0.4459 | 0.4459 | 0.4360 | 1102.9349 | 2 |

## Gate

- Chunk-level graded qrels use grade >= 2 as direct evidence for Recall/MRR.
- nDCG retains all reviewed grades 0-3; no-answer cases are excluded from ranking means.
- A candidate must avoid quality regression, keep successful-case rate at 1.0, stay within +750 ms and 2x Dense P95, and show a strict quality gain.
- A `NO_GO` result keeps public Schema `1.0` and `dense-v1` unchanged.

### bm25

- recall_at_k regression
- mrr_at_k regression
- ndcg_at_k regression
- no strict quality gain over dense

### hybrid

- recall_at_k regression
- ndcg_at_k regression

### rerank

- p95 increase > 750 ms
- p95 exceeds 2x dense
