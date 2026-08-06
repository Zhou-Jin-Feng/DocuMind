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
  "top_k": 3
}
```

`expected_document_ids` is a logical document identifier. A real adapter must expose the same stable value through `metadata.document_id`; filenames and absolute paths are not evaluation identifiers.

No-answer cases use an empty `expected_document_ids` list and `should_answer: false`:

```json
{"id":"rag-out-of-scope","question":"明天股票会涨吗？","expected_document_ids":[],"expected_keywords":[],"should_answer":false,"top_k":3}
```

## Metrics

The runner reports:

- `recall_at_k`: expected documents found in Top-K divided by expected documents;
- `precision_at_k`: relevant retrieved documents divided by K;
- `mrr_at_k`: reciprocal rank of the first relevant document;
- `top_k_hit_rate`: ratio of answerable cases with at least one expected document in Top-K;
- `correct_document_avg_rank`: average rank of the first relevant document;
- `refusal_accuracy`: agreement between `should_answer` and the answer adapter;
- `keyword_coverage`: expected keyword coverage when an answer adapter returns text;
- `successful_case_rate` and `average_duration_ms`.

No-answer cases are excluded from retrieval metrics because they have no positive document target. They remain included in refusal accuracy when an answer adapter is configured.

## Offline Demo

Run the deterministic demo without Ollama, ChromaDB, network access, or an LLM:

```powershell
.\venv\Scripts\python.exe -m evaluation.runner `
  --dataset evaluation/datasets/golden_dataset.jsonl `
  --output-json evaluation/reports/demo.json `
  --output-markdown evaluation/reports/demo.md
```

The demo adapter is intentionally perfect. Its purpose is to validate dataset parsing, report generation, and the evaluation pipeline, not to claim production retrieval quality.

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

## Scope

This version deliberately does not add Docker, Prometheus/Grafana containers, Celery, Redis, authentication, query rewriting, or a production reranker. Those remain later roadmap items.
