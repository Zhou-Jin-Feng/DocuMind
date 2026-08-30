# P2 Retrieval Candidate Decision

Decision: **NO_GO**

Selected candidate: `none`

Public contract action: `keep_schema_1_0_dense_v1`

## Evidence

| Item | Value |
|---|---:|
| Total cases | 35 |
| Validation cases | 20 |
| Holdout cases | 15 |
| Holdout answerable / no-answer | 5 / 10 |

## Holdout Comparison

| Mode | Eligible | Recall@K | MRR@K | No-answer | P95 ms | Failures |
|---|---|---:|---:|---:|---:|---:|
| `dense` | baseline | 1.0000 | 1.0000 | 0.0000 | 163.6396 | 0 |
| `bm25` | no | 1.0000 | 1.0000 | 0.0000 | 0.5842 | 1 |
| `hybrid` | no | 1.0000 | 1.0000 | 0.0000 | 166.9436 | 1 |
| `rerank` | no | 1.0000 | 0.9000 | 0.0000 | 2237.6186 | 4 |

## Diagnostic Signals

| Mode | Answerable Top-1 | Rank improved / regressed | Changed ranks | No-answer non-empty | Holdout duration range |
|---|---:|---:|---:|---:|---:|
| `dense` | 1.0000 | 0 / 0 | 0 | 1.0000 | 115.9 - 169.4 |
| `bm25` | 1.0000 | 0 / 0 | 5 | 1.0000 | 0.3 - 0.6 |
| `hybrid` | 1.0000 | 0 / 0 | 4 | 1.0000 | 110.3 - 172.8 |
| `rerank` | 0.8000 | 0 / 1 | 5 | 1.0000 | 1556.1 - 2533.7 |

`Answerable Top-1` exposes the quality headroom that aggregate MRR can hide; `No-answer non-empty` is the fraction of no-answer cases that still returned candidates. The current comparison uses no rejection threshold, so the latter is not a refusal-quality score.

## Candidate Findings

### bm25

- bm25: no material holdout quality gain

### hybrid

- hybrid: no material holdout quality gain

### rerank

- rerank: mrr_at_k regressed by 0.1000
- rerank: no material holdout quality gain
- rerank: P95 increase 2074.0 ms exceeds 750.0 ms
- rerank: P95 multiplier 13.674 exceeds 2.000

A `GO` result authorizes review of the selected candidate; it does not change the public API automatically. A `NO_GO` result keeps Schema `1.0` and `dense-v1` unchanged.
