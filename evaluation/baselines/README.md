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
