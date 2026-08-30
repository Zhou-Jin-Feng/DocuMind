# P2 DS-03 Normalization Evidence

- Schema: `p2-normalized-snapshot-v1`
- Manifest SHA-256: `87fdbfa691696f1246bfc56fe9137c67cc21bd71a349ca78cb295e9ad551369e`
- Snapshot file SHA-256: `3dfcccd528ac9536140de28c6d7217824dd22c8163b1acab3d37ba89c0645100`
- Dataset SHA-256: `05096037d6cdd2ae9667e66616ae1f55c8236383f0a72f559f4f1846618fbaaa`

## Counts And Fingerprints

| Source | Documents | Queries | Qrels | Dataset SHA-256 |
|---|---:|---:|---:|---|
| `t2ranking-mteb-dev` | 118605 | 22812 | 118932 | `12eb27fd5534eec0e72bf2ebf5a35766cc58a9d49155e65ee78d0a99f0eb52f2` |
| `beir-nfcorpus` | 3633 | 3237 | 134294 | `e1d62bc72f0dabbb99044d244786c118560c07860dab6e61f202ad996e625189` |
| `beir-scifact` | 5183 | 1109 | 1258 | `a661cade883e2c0dc0ded35275fdb9b27617aa37e52da8a7866de72556f02871` |
| **Total** | **127421** | **27158** | **254484** | - |

## Boundary

This report records deterministic local normalization only. Raw and normalized text remains Git-ignored. No Embedding, Milvus indexing, model call, public API change or candidate rollout is authorized by this evidence.
