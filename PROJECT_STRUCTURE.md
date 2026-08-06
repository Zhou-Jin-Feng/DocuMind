# 项目结构（v1.3）

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
│   └── *.txt
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
| `retriever.py` | Query Embedding、距离阈值、轻量重排、检索 Span 与 Metrics |
| `generator.py` | OpenAI 兼容/Anthropic 消息适配和流式生成 |
| `web_app.py` | 上传校验、同步索引、问答编排、根 Span、Metrics 服务和 UI |
| `observability/context.py` | `request_id` / `trace_id` 的 ContextVar 生命周期 |
| `observability/logging.py` | 结构化日志、标准字段、JSONL 输出和敏感信息脱敏 |
| `observability/metrics.py` | Prometheus 指标定义、低基数标签和显式 HTTP 服务启动 |
| `observability/tracing.py` | 私有 TracerProvider、核心 Span、错误标记和 OTLP/HTTP 导出 |
| `utils/logger.py` | 兼容旧导入路径，转发到结构化日志模块 |
| `utils/monitoring.py` | `perf_counter()` 计时和生成器完整迭代耗时 |

## 依赖方向

```text
web_app.py
├── app.config
├── app.core.*
└── app.observability.*

app.core.retriever
├── app.observability.metrics
└── app.observability.tracing
```

可观测性模块不得反向导入 Web UI 或具体 RAG 组件，避免循环依赖。

## 运行数据边界

以下目录不得提交到 Git：

- `data/chroma_db/`
- `data/uploads/`
- `logs/`
- `venv/`
- `__pycache__/`
- `.env`
