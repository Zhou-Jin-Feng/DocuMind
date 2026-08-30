# P2 DS-05 Split Isolation And Leakage Audit

- Status: `passed`
- Dataset: `p2-retrieval-v2`
- Gold SHA-256: `3cca068f504f5604389b251400a097915d0a0e82b45fd06f6fcab095eccb71a1`
- Freeze SHA-256: `49600e59d3525ac78ffadb61f667004db42752e0b80ad1bccce4e383ae4472a2`

## Frozen Splits

| Split | Cases | Topics | Fact families | Documents | Chunks | Records SHA-256 |
|---|---:|---:|---:|---:|---:|---|
| validation | 50 | 6 | 50 | 15 | 24 | `8ab813bae1a508e6aa4c4583788d475c3d3faf108b18a7008b323cb43790fc04` |
| holdout | 50 | 6 | 50 | 15 | 24 | `54e73352e3f665a75b546507f0374118619d4161a64f5cf5d3e23bb836cfc215` |

## Cross-Split Checks

| Check | Overlap count |
|---|---:|
| case_ids | 0 |
| normalized_questions | 0 |
| fact_family_ids | 0 |
| topic_ids | 0 |
| document_ids | 0 |
| chunk_ids | 0 |
| qrel_pair_ids | 0 |
| evidence_control_ids | 0 |
| evidence_quote_hashes | 0 |

High-confidence near-duplicate threshold: `0.95`.
Near-duplicate question pairs: `0`.

No raw question or document text is included in this report. Any non-zero finding blocks the DS-05 gate and requires review before evaluation.
