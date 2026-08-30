# DS-02 Acquisition Evidence

- Status: `PASS`
- Files: `12`
- Bytes: `169682657`
- Sources: `t2ranking-mteb-dev, beir-nfcorpus, beir-scifact`

## Structure

| Source | Corpus rows | Query rows | Qrel rows |
|---|---:|---:|---:|
| `t2ranking-mteb-dev` | 118605 | 22812 | 118932 |
| `beir-nfcorpus` | 3633 | 3237 | 134294 |
| `beir-scifact` | 5183 | 1109 | 1258 |

## Bounded Pilots

- Parquet sample read: `3000` rows in `0.0417` s (`72019.3` rows/s).
- Ollama embedding: `32` passages, batch `8`, dimension `4096`.
- Embedding sample sources: `{'t2ranking-mteb-dev': 32}`; measured batches: `4`.
- Warmed measured throughput: `2.96` passages/s; batch P95 `3.933` s.
- MIRACL embedding-only directional projection: `462.6` hours.
- Projection excludes vector-store writes/indexing, WAL, retries and dataset length-distribution differences.

## MIRACL Decision

- Decision: `DEFER_FULL_DOWNLOAD`.
- Raw float32 vectors alone: `80844685312` bytes; projected free disk after raw snapshot and vectors: `109081585839` bytes.
- Meets the 120 GiB floor before Milvus overhead: `false`.
- Meets the 18-hour launch projection limit: `false` (embedding-only projection `462.6` hours).
- Meets the 24-hour end-to-end hard limit: `false`.
- Eligible to start: `false`.
- License status: `UNRESOLVED_CONFLICT`.
- Reopen only after license provenance is resolved and DS-03 freezes a deterministic subset or hard-negative protocol that avoids full-corpus Dense indexing.

## Boundary

This evidence validates acquisition, file integrity, raw schema and a bounded local pilot. It does not authorize MIRACL acquisition, full-corpus embedding, public API changes or a retrieval-candidate rollout.
