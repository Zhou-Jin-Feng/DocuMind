# 项目结构（v1.6）

```text
DocuMind/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── document_loader.py
│   │   ├── document_chunker.py
│   │   ├── embedding_client.py
│   │   ├── vector_store.py
│   │   ├── retriever.py
│   │   └── generator.py
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── context.py
│   │   ├── logging.py
│   │   ├── metrics.py
│   │   └── tracing.py
│   ├── lifecycle/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py
│   │   ├── models.py
│   │   ├── registry.py
│   │   └── service.py
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── monitoring.py
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_document_pipeline.py
│   ├── test_embedding_client.py
│   ├── test_vector_store.py
│   ├── test_retriever.py
│   ├── test_generator.py
│   ├── test_web_app.py
│   ├── test_observability_context.py
│   ├── test_structured_logging.py
│   ├── test_observability_events.py
│   ├── test_monitoring.py
│   ├── test_metrics.py
│   ├── test_tracing.py
│   ├── test_evaluation.py
│   ├── test_lifecycle.py
│   ├── test_lifecycle_cli.py
│   └── *.txt
├── evaluation/
│   ├── __init__.py
│   ├── adapters.py
│   ├── integration.py
│   ├── fingerprints.py
│   ├── production.py
│   ├── production_runner.py
│   ├── metrics.py
│   ├── models.py
│   ├── regression.py
│   ├── regression_runner.py
│   ├── reports.py
│   ├── runner.py
│   ├── datasets/
│   │   ├── golden_dataset.jsonl
│   │   ├── documents/
│   │   └── v1_6/
│   │       ├── golden_dataset.jsonl
│   │       └── documents/
│   ├── baselines/
│   └── reports/
├── data/                  # 本地运行数据，Git 忽略
├── logs/                  # JSONL 日志，Git 忽略
├── .env                   # 本地密钥，Git 忽略
├── .env.example           # 无密钥配置模板
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── ARCHITECTURE.md
├── DEPENDENCIES.md
├── OBSERVABILITY.md
├── EVALUATION.md
├── PROJECT_STRUCTURE.md
└── web_app.py
```

## 模块职责

| 文件 | 职责 |
|---|---|
| `app/config.py` | 环境变量加载、默认值和参数验证 |
| `document_loader.py` | PDF/DOCX/TXT 加载、稳定文档 ID、页码元数据 |
| `document_chunker.py` | 文档分块、稳定 Chunk ID、空块过滤 |
| `embedding_client.py` | Ollama 和 API Embedding 统一调用 |
| `vector_store.py` | Chroma 持久化、upsert、search、delete |
| `retriever.py` | Dense 检索、BM25 中文/标识符分词、RRF 融合、结果分数契约、检索 Span 与 Metrics |
| `generator.py` | OpenAI 兼容/Anthropic 消息适配和流式生成 |
| `web_app.py` | 上传校验、生命周期服务调用、问答编排、根 Span、Metrics 服务和 UI |
| `app/lifecycle/models.py` | 文档、版本、索引清单、操作结果和审计报告模型 |
| `app/lifecycle/registry.py` | SQLite 文档、索引、操作状态和 active 指针 |
| `app/lifecycle/service.py` | 源文件持久化、同步构建、active 切换、清理、审计和重建 |
| `app/lifecycle/cli.py` | `list`、`audit`、`cleanup`、`rebuild` 运维命令 |
| `observability/context.py` | `request_id` / `trace_id` 的 ContextVar 生命周期 |
| `observability/logging.py` | 结构化日志、标准字段、JSONL 输出和敏感信息脱敏 |
| `observability/metrics.py` | Prometheus 指标定义、低基数标签和显式 HTTP 服务启动 |
| `observability/tracing.py` | 私有 TracerProvider、核心 Span、错误标记和 OTLP/HTTP 导出 |
| `utils/logger.py` | 兼容旧导入路径，转发到结构化日志模块 |
| `utils/monitoring.py` | `perf_counter()` 计时和生成器完整迭代耗时 |
| `evaluation/models.py` | 黄金用例、问题类别、检索结果和分类评估报告数据模型 |
| `evaluation/metrics.py` | Recall@K、Precision@K、MRR、命中率和拒答指标 |
| `evaluation/adapters.py` | Dense、BM25、Hybrid Retriever 适配器与离线 Fake Adapter |
| `evaluation/integration.py` | 确定性 Embedding、内存 Vector Store 和三种检索模式集成烟囱测试 |
| `evaluation/fingerprints.py` | 黄金数据集和评估文档语料的稳定 SHA-256 指纹 |
| `evaluation/production.py` | Dense、BM25 和 Hybrid 生产组件评估装配 |
| `evaluation/production_runner.py` | 真实 Provider 三种检索模式基线 CLI |
| `evaluation/runner.py` | JSONL 黄金评估集加载、分类汇总和确定性三模式执行 |
| `evaluation/regression.py` | 指标最低值和允许下降幅度门禁 |
| `evaluation/regression_runner.py` | 报告兼容性校验和自动回归门禁 CLI |
| `evaluation/reports.py` | JSON/Markdown 报告文件输出 |

## 依赖方向

```text
web_app.py
├── app.config
├── app.core.*
├── app.lifecycle.*
└── app.observability.*

app.lifecycle.service
├── app.core.document_loader
├── app.core.document_chunker
├── app.core.vector_store
└── app.lifecycle.registry

app.core.retriever
├── app.observability.metrics
└── app.observability.tracing
```

可观测性模块不得反向导入 Web UI 或具体 RAG 组件，避免循环依赖。

## 运行数据边界

以下目录不得提交到 Git：

- `data/chroma_db/`
- `data/uploads/`
- `data/document_registry.sqlite3`
- `logs/`
- `venv/`
- `__pycache__/`
- `.env`
