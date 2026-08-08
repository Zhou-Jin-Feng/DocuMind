# DocuMind - RAG Evaluation

v1.4 introduces an offline golden dataset and regression runner. It evaluates retrieval behavior without changing the Gradio application or calling a real LLM.

## Dataset

The default dataset is `evaluation/datasets/golden_dataset.jsonl`. Each non-empty line is one strict JSON object:

```json
{
  "id": "rag-core-components",
  "question": "RAG 系统包含哪些核心组件？",
  "expected_document_ids": ["knowledge-base"],
  "expected_keywords": ["文档加载", "分块", "向量数据库", "检索", "生成"],
  "should_answer": true,
  "top_k": 3,
  "category": "exact_term"
}
```

`expected_document_ids` is a logical document identifier. A real adapter must expose the same stable value through `metadata.document_id`; filenames and absolute paths are not evaluation identifiers.

No-answer cases use an empty `expected_document_ids` list and `should_answer: false`:

```json
{"id":"rag-out-of-scope","question":"明天股票会涨吗？","expected_document_ids":[],"expected_keywords":[],"should_answer":false,"top_k":3}
```

`category` is optional for old datasets and defaults to `general`. The v1.6 dataset uses `exact_term`, `semantic_paraphrase`, `keyword_precision`, `hard_negative`, `multi_hop`, and `no_answer`; reports include a separate metric table for every category.

`split` is also optional and defaults to `all` for backward compatibility. Supported values are `all`, `train`, `validation`, and `holdout`. Reports aggregate the same metrics by category and by split. The v1.6.1 holdout cases live in `evaluation/datasets/v1_6/holdout_dataset.jsonl`; keep them separate from tuning cases and use them for final calibration checks.

## Metrics

The runner reports:

- `recall_at_k`: expected documents found in Top-K divided by expected documents;
- `precision_at_k`: unique relevant document IDs in Top-K divided by K; multiple
  chunks from the same document count once;
- `mrr_at_k`: reciprocal rank of the first relevant document;
- `top_k_hit_rate`: ratio of answerable cases with at least one expected document in Top-K;
- `correct_document_avg_rank`: average rank of the first relevant document;
- `no_answer_retrieval_accuracy`: ratio of no-answer cases that return no Top-K documents;
- `refusal_accuracy`: agreement between `should_answer` and the answer adapter;
- `keyword_coverage`: expected keyword coverage when an answer adapter returns text;
- `successful_case_rate`, `average_duration_ms`, `p50_duration_ms`,
  `p95_duration_ms`, and `maximum_duration_ms`.

No-answer cases are excluded from positive-target retrieval metrics because they have no relevant document ID. They are included in `no_answer_retrieval_accuracy`; with no distance threshold, a vector store will normally return an irrelevant nearest document and this metric will expose that behavior. They remain included in refusal accuracy when an answer adapter is configured.

## Offline Demo

Run the deterministic demo without Ollama, ChromaDB, network access, or an LLM:

```powershell
.\venv\Scripts\python.exe -m evaluation.runner `
  --dataset evaluation/datasets/golden_dataset.jsonl `
  --output-json evaluation/reports/demo.json `
  --output-markdown evaluation/reports/demo.md
```

The default demo loads the sample documents and exercises the production `Retriever` through a deterministic hash Embedding and in-memory Vector Store. The answerability adapter remains fake. The demo is intentionally deterministic: its purpose is to validate the real retrieval boundary, dataset parsing, report generation, and the evaluation pipeline, not to claim production retrieval quality.

### v1.6 Retrieval Comparison

The expanded dataset is stored in `evaluation/datasets/v1_6/` and contains 32 cases over 9 engineering documents. Run the three deterministic comparisons with `--retrieval-mode dense`, `bm25`, or `hybrid`. Checked-in reports are `evaluation/reports/v1_6_{dense,bm25,hybrid}.{json,md}`.

| Mode | Recall@3 | MRR@3 | Hit Rate | No-answer Accuracy |
|---|---:|---:|---:|---:|
| Dense hash smoke | 0.2593 | 0.1173 | 0.2593 | 0.0000 |
| BM25-only | 0.9630 | 0.9012 | 0.9630 | 0.0000 |
| Equal-weight RRF | 0.5556 | 0.4136 | 0.5556 | 0.0000 |

The hash Dense backend is intentionally simple and is not a production semantic model. Equal-weight RRF improves over that Dense smoke but underperforms BM25 because the weak Dense ranking still contributes equally. This is evidence to run the same comparison with the intended real Embedding model, not evidence to tune weights against the small fixture set or switch Web defaults. All unthresholded modes still force some irrelevant candidates for no-answer questions, so abstention thresholds require separate calibration.

The production baseline CLI accepts the same modes:

```powershell
.\venv\Scripts\python.exe -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/golden_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --retrieval-mode hybrid `
  --provider ollama
```

BM25-only does not call an Embedding provider and rejects `--score-threshold`. Hybrid uses RRF ranks and never compares Chroma distance with BM25 scores directly.

### v1.6.1 Retrieval Calibration

v1.6.1 adds a separate 12-case holdout set and makes Hybrid calibration explicit. The CLI options are:

- `--dense-weight` and `--lexical-weight`: non-negative RRF channel weights; they cannot both be zero;
- `--rrf-k`: positive RRF smoothing constant;
- `--candidate-multiplier`: positive candidate-depth multiplier;
- `--score-threshold`: maximum accepted Dense distance;
- `--lexical-score-threshold`: minimum accepted BM25 score.

All values are written to report metadata. A zero-weight channel is not queried. The Web application remains Dense-only and does not consume these experimental settings.

The checked-in real-provider reports use local Ollama `qwen3-embedding` (4096 dimensions), 9 documents, 10 production chunks, and the 12 holdout cases:

| Mode | Recall@3 | MRR@3 | No-answer Accuracy | Result |
|---|---:|---:|---:|---|
| Dense, no threshold | 1.0000 | 1.0000 | 0.0000 | baseline |
| BM25, no threshold | 1.0000 | 0.9394 | 0.0000 | baseline |
| Equal-weight Hybrid, no threshold | 1.0000 | 1.0000 | 0.0000 | baseline |
| Dense, distance <= 1.0 | 1.0000 | 1.0000 | 1.0000 | calibrated candidate |
| Hybrid, distance <= 1.0 and BM25 >= 12.2 | 1.0000 | 0.9545 | 1.0000 | calibrated candidate |

Run the calibrated Hybrid candidate and its holdout gate:

```powershell
.\venv\Scripts\python.exe -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2 `
  --dense-weight 1.0 --lexical-weight 1.0 `
  --rrf-k 60 --candidate-multiplier 5

.\venv\Scripts\python.exe -m evaluation.regression_runner `
  --baseline evaluation/reports/v1_6_1_ollama_holdout_hybrid.json `
  --current evaluation/reports/v1_6_1_ollama_holdout_hybrid_calibrated.json `
  --allowed-drop mrr_at_k=0.05 `
  --minimum recall_at_k=1.0 `
  --minimum no_answer_retrieval_accuracy=1.0 `
  --minimum successful_case_rate=1.0
```

These thresholds are calibrated evidence for this fixture corpus, not online defaults. Revalidate them after changing the corpus, chunking, provider, model, or distance metric.

For a real baseline, replace the deterministic integration components with a real `RetrieverAdapter` backed by the intended Embedding model and vector collection. Keep the same document IDs and golden dataset when comparing changes.

The reusable production wiring is exposed by `build_configured_retrieval_adapter()`. It uses the configured real Embedding provider, the production chunker, Chroma `VectorStore`, and the production `Retriever`. Calling it may contact Ollama or a cloud API and should be done deliberately when creating a baseline.

Create a real retrieval-only baseline with the CLI. The command does not call an LLM, so answer-generation metrics remain `N/A`:

```powershell
.\venv\Scripts\python.exe -m evaluation.production_runner `
  --provider ollama `
  --persist-directory .\data\evaluation_chroma_db
```

The CLI explicitly releases the Chroma adapter before exit. Use a separate collection and persistence directory from the application index.

### Current Ollama Baseline

The checked-in Ollama reports were generated with `qwen3-embedding` (4096 dimensions), 5 short fixture documents, and 8 cases: 6 answerable questions and 2 no-answer questions. These are real local Ollama calls, but the dataset is a small engineering baseline rather than statistically representative production evidence.

Without a distance threshold, the 6 answerable cases all place their target document at rank 1 (`Recall@3=1.0`, `MRR@3=1.0`), while both no-answer cases still return irrelevant nearest documents (`no_answer_retrieval_accuracy=0.0`). `Precision@3=0.3333` is expected because each answerable case labels one relevant document while the retriever returns three. `successful_case_rate=1.0` means all calls completed without exceptions; it is not an answer-quality score.

With the experimental maximum distance threshold `1.0`, the same sample keeps `Recall@3=1.0` and raises `no_answer_retrieval_accuracy` to `1.0`. This threshold is only a candidate derived from two negative examples. It must not become the online default until the dataset contains more realistic documents, paraphrases, hard negatives, and domain-specific no-answer questions.

The reports record the Provider, model, actual vector dimension, chunk settings, Top-K values, threshold, and dataset sizes. Local latency is a hardware snapshot and should only be compared under the same machine and service conditions.

## v1.7 Query Rewrite And Reranker

v1.7 keeps the Web application unchanged and introduces two evaluation-only stages:

- Query Rewrite always retains the normalized original question as the first query. The LLM response must be one strict JSON object, `{"queries":[...]}`; empty, duplicate, markdown-wrapped, or extra-field responses fail the case instead of silently changing retrieval behavior.
- Multi-query retrieval runs each query independently, deduplicates only by stable `metadata.chunk_id`, and uses a second RRF layer over ranks. It does not compare raw scores across queries.
- Cross-Encoder reranking receives an expanded candidate set and writes `rerank_score` without replacing `distance`, `lexical_score`, Hybrid `fusion_score`, or Query RRF `query_fusion_score`.

`evaluation.rewrite_runner` separates external LLM generation from retrieval evaluation. It creates a strict, versioned artifact containing the provider, model, generation parameters, prompt SHA-256, dataset SHA-256, and the alternatives for every question. `evaluation.production_runner --rewrite-map` rejects an artifact with a different dataset fingerprint, question set, unsupported schema version, or a requested rewrite count above the artifact generation limit, so a later local run is deterministic with respect to its LLM inputs.

```powershell
python -m evaluation.rewrite_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --provider deepseek --model deepseek-chat `
  --max-rewrites 2 `
  --max-tokens 256 `
  --output evaluation/datasets/v1_7/holdout_rewrites_deepseek.json

python -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2 `
  --enhancement-mode rewrite `
  --rewrite-map evaluation/datasets/v1_7/holdout_rewrites_deepseek.json
```

The production runner supports `baseline`, `rewrite`, `rerank`, and `rewrite-rerank` modes. Every report records the enhancement mode and all enabled-stage parameters. A cached Cross-Encoder can be forced offline with `--reranker-local-files-only`, which prevents per-case Hugging Face metadata checks in restricted environments.

```powershell
python -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2 `
  --enhancement-mode rerank `
  --reranker-model BAAI/bge-reranker-base `
  --reranker-batch-size 8 --reranker-device cpu `
  --reranker-local-files-only
```

The original v1.7.0 rerank report uses local Ollama `qwen3-embedding`, `BAAI/bge-reranker-base` on CPU, the same 12-case holdout, and the calibrated Hybrid baseline:

| Mode | Recall@3 | MRR@3 | No-answer Accuracy | Success | Avg Duration |
|---|---:|---:|---:|---:|---:|
| v1.6.1 calibrated Hybrid | 1.0000 | 0.9545 | 1.0000 | 1.0000 | 420.7 ms |
| v1.7 calibrated Hybrid + Reranker | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 937.9 ms |

The reranker fixed the observed ranking error but added approximately 517.2 ms on this CPU. This historical single-mode result motivated the complete v1.7.1 comparison below; it did not authorize a Web default change.

v1.7.1 regenerates all four reports with latency percentiles. After the
individual regression gates pass, create one strict comparison artifact. The
comparison rejects missing modes, wrong `enhancement_mode` labels, or changes
to the dataset, corpus, Embedding, chunking, retrieval, threshold, and Hybrid
configuration:

```powershell
python -m evaluation.comparison_runner `
  --baseline evaluation/reports/v1_7_1_ollama_holdout_hybrid_baseline.json `
  --rewrite evaluation/reports/v1_7_1_ollama_holdout_hybrid_rewrite.json `
  --rerank evaluation/reports/v1_7_1_ollama_holdout_hybrid_rerank.json `
  --rewrite-rerank evaluation/reports/v1_7_1_ollama_holdout_hybrid_rewrite_rerank.json
```

The JSON comparison stores each mode's metrics and `mode - baseline` deltas.
Quality and latency remain separate instead of being collapsed into one
subjective score. P50/P95/max include lazy model loading, so the first-case
cold-start cost remains visible.

The final v1.7.1 run produced the following same-configuration results:

| Mode | Recall@3 | Precision@3 | MRR@3 | No-answer | Avg ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1.0000 | 0.3333 | 0.9545 | 1.0000 | 308.3 | 308.7 | 325.7 |
| rewrite | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 890.2 | 878.5 | 961.4 |
| rerank | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 1018.9 | 690.0 | 2462.0 |
| rewrite-rerank | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 1742.6 | 1674.4 | 2608.7 |

All three enhanced modes fix the same single baseline ranking error and pass
the regression gate. Rewrite is the preferred candidate for a later bounded
integration experiment because it matches reranking quality with substantially
lower P95 latency. The combined mode adds latency without measured quality gain
and should remain disabled. The 12-case holdout is too small to change the Web
default on its own.

## Regression Gate

Compare a current report with a saved baseline in Python:

```python
from evaluation.models import EvaluationReport
from evaluation.regression import RegressionGate

gate = RegressionGate(
    allowed_drops={"recall_at_k": 0.02, "mrr_at_k": 0.02},
    minimums={"successful_case_rate": 1.0},
)
result = gate.evaluate(baseline_report, current_report)
result.assert_passed()
```

The gate uses absolute metric drops. A missing current metric fails when the baseline had a numeric value; a metric that is not applicable in both reports is skipped.

Run the automatic CLI gate against two JSON reports:

```powershell
.\venv\Scripts\python.exe -m evaluation.regression_runner `
  --baseline evaluation/reports/ollama_retrieval_baseline.json `
  --current evaluation/reports/current.json
```

The default policy allows an absolute drop of `0.02` for Recall, Precision, MRR, and Top-K hit rate, allows no drop in no-answer retrieval accuracy, and requires `successful_case_rate=1.0`. Use repeated `--allowed-drop METRIC=VALUE` and `--minimum METRIC=VALUE` arguments to override or add rules. `--no-default-policy` disables the built-in rules.

Exit codes are stable for local scripts and CI: `0` means pass, `1` means a quality regression, and `2` means invalid input or incompatible reports. Before checking metrics, the CLI requires matching dataset name, Top-K, case count, golden-dataset SHA-256, document-corpus SHA-256, and every shared Embedding, chunking, threshold, retrieval, and Hybrid configuration field. Reports that intentionally change those inputs belong to a calibration comparison, not a regression gate. Duplicate JSON keys are rejected before comparison.

`correct_document_avg_rank` is intentionally absent from the default policy because lower values are better; the current `allowed-drop` policy is only for metrics where larger values are better.

## Scope

This version deliberately keeps Query Rewrite and Cross-Encoder Reranking out of the Web request path. Docker, Prometheus/Grafana containers, Celery, Redis, authentication, online history-aware retrieval, and a production rollout policy remain later roadmap items.
