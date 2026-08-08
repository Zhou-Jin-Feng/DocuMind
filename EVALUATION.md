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

## Metrics

The runner reports:

- `recall_at_k`: expected documents found in Top-K divided by expected documents;
- `precision_at_k`: relevant retrieved documents divided by K;
- `mrr_at_k`: reciprocal rank of the first relevant document;
- `top_k_hit_rate`: ratio of answerable cases with at least one expected document in Top-K;
- `correct_document_avg_rank`: average rank of the first relevant document;
- `no_answer_retrieval_accuracy`: ratio of no-answer cases that return no Top-K documents;
- `refusal_accuracy`: agreement between `should_answer` and the answer adapter;
- `keyword_coverage`: expected keyword coverage when an answer adapter returns text;
- `successful_case_rate` and `average_duration_ms`.

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

Exit codes are stable for local scripts and CI: `0` means pass, `1` means a quality regression, and `2` means invalid input or incompatible reports. Before checking metrics, the CLI requires matching dataset name, Top-K, case count, golden-dataset SHA-256, and document-corpus SHA-256. Embedding model, chunk settings, and score threshold may differ because those are the configurations being evaluated.

`correct_document_avg_rank` is intentionally absent from the default policy because lower values are better; the current `allowed-drop` policy is only for metrics where larger values are better.

## Scope

This version deliberately does not add Docker, Prometheus/Grafana containers, Celery, Redis, authentication, query rewriting, or a production reranker. Those remain later roadmap items.
