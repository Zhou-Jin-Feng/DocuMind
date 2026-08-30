# Evaluation Baselines

Baseline files store the quality metrics that a later change must not reduce
beyond the configured tolerance. These deterministic files are pipeline smoke
baselines; they are not claims about production RAG or final-answer quality.

## Active Deterministic Baseline

`deterministic_dense_v2.json` is the active Dense baseline for the v2.0.1
hardening series. Its matching human-readable report is
`deterministic_dense_v2.md`.

It was generated on 2026-08-18 from the v2.0.1 task working tree based on
`main@07d9433`, using:

```powershell
.\venv\Scripts\python.exe -m evaluation.runner `
  --dataset evaluation/datasets/golden_dataset.jsonl `
  --retrieval-mode dense `
  --output-json evaluation/baselines/deterministic_dense_v2.json `
  --output-markdown evaluation/baselines/deterministic_dense_v2.md
```

The reviewed run contains 8 successful cases and records the complete current
retrieval configuration. Its logical-text fingerprints are:

- dataset: `81741dfc4e4a59698b45ba2565558203aa0f7906c077f98749eb88ce512019a6`
- documents: `645e477edbcd6086226621abb76ddfa147b44acf56c632edf39e89e8220298b3`

Reviewed artifact fingerprints:

- JSON report: `0470a8f296705e861a08997fd993fddac1fe5fb8af907b34bf66f3ab44310c61`
- Markdown report: `2790259078622057d60fe2a969cbb5222de680d1716c40ce685b5334e8bcbf21`

The review confirmed that all non-latency metrics match the historical demo
baseline. Recall@3 remains `0.8333`, and no-answer retrieval accuracy remains
`0.0`; this baseline prevents silent regressions but is not a quality target.
Its `refusal_accuracy=1.0` comes from the deterministic fake answer mapping and
does not measure a real LLM.

The same working tree was mounted read-only into the local Linux
`rag-stack-api:latest` image. A fresh Linux report produced the same input
fingerprints and non-latency metrics, and the regression CLI returned `PASS`.

`demo_baseline.json` remains a historical v2.0 artifact. It is not compatible
with current Runner metadata and must not be used by new CI jobs.

Create a real baseline only after running the same golden dataset through a
real or test-isolated retrieval adapter. Do not compare reports generated from
different datasets, Top-K values, document IDs, embedding models, or other
compatibility metadata.

## Single-document API Contract Baseline

`retrieve_quality_v1.json` and `retrieve_quality_v1.md` are the P1 contract and
isolation baseline for `POST /api/v1/retrieve`. They use two documents, six
chunks and five cases through the production `RetrievalService`, backed only by
repository-local deterministic evaluation dependencies.

Generate and gate a current report with:

```powershell
.\venv\Scripts\python.exe -m evaluation.retrieve_quality_runner `
  --json-output evaluation/reports/retrieve_quality_current.json `
  --markdown-output evaluation/reports/retrieve_quality_current.md

.\venv\Scripts\python.exe -m evaluation.regression_runner `
  --baseline evaluation/baselines/retrieve_quality_v1.json `
  --current evaluation/reports/retrieve_quality_current.json `
  --allowed-drop ndcg_at_k=0 `
  --minimum api_bottom_parity_rate=1 `
  --minimum contamination_free_rate=1 `
  --minimum no_answer_empty_accuracy=1
```

Logical input fingerprints:

- dataset: `0a3b71a25f7aefd73df006d622d5b404ca418e9a1672f4272167c4ee430f26e2`
- documents: `f83815e7cceb4ed135e19d263916bfc1a8bb18536ecd2e98a8165c8306efca8a`

Reviewed artifact fingerprints:

- JSON report: `da64533970ab54344994b9b405d9f59befec2f911ef73dd1e475de0d2ca849f4`
- Markdown report: `a49ed6afc9f7fb8d9bf2a76ba21c9932342020d3a5d661880099c1cce12d22d3`

All invariant and positive quality metrics are `1.0`, except Precision@2 is
`0.5` because each positive case labels one relevant chunk. This is an offline
contract regression, not evidence about real Embedding or Milvus quality.

## P2 Retrieval Candidate Decision

`p2_retrieval_candidate_decision_v1.json` and its readable Markdown companion
freeze the P2-01 `NO_GO` decision. Unlike the deterministic regression
baselines, this artifact references four real comparison reports generated from
the same 35-case validation/holdout dataset, 11-document corpus and production
chunk settings.

The gate verifies exact evidence compatibility and source-report SHA-256 values
before comparing Dense with BM25, Hybrid and Hybrid plus Reranker. On this
11-Chunk fixture, answerable Dense was already Top-1 in every holdout case, so
BM25 and Hybrid produced no measurable gain that could pass the policy; this is
evidence of no gain on the frozen fixture, not a general claim that lexical or
hybrid retrieval never helps. Reranking reduced holdout MRR from `1.0` to `0.9`
and increased P95 from `163.6 ms` to `2237.6 ms`.

The decision artifact also records diagnostic signals: answerable Top-1 rates,
per-case rank changes, no-answer non-empty rates, and holdout duration ranges.
All modes returned non-empty results for the ten no-answer cases because this
comparison intentionally used no rejection threshold; that value must not be
read as a refusal-quality result.
Therefore the public contract remains Schema `1.0` and `dense-v1`.

Reviewed decision artifact fingerprints:

- JSON decision: `75afc60d7389d7fea1952ae58ff145027e3f5021bd7cd381e8cbe8a5de529428`
- Markdown decision: `1546879bea6fb7b4b2d379da217c1621ccba844d306569cb3796a97f2225888c`

The decision runner returns `1` for a valid `NO_GO`; this is a product decision,
not malformed evidence. A later experiment must write a new versioned artifact
instead of replacing this reviewed result.
