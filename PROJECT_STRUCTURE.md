# 项目结构（v2.0）

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
│   │   ├── query_rewriter.py
│   │   ├── reranker.py
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
│   ├── services/
│   │   ├── __init__.py
│   │   ├── rag_service.py
│   │   └── document_service.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── main.py
│   │   ├── dependencies.py
│   │   ├── errors.py
│   │   ├── schemas.py
│   │   ├── sse.py
│   │   └── routers/
│   │       ├── health.py
│   │       ├── system.py
│   │       ├── documents.py
│   │       └── chat.py
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
│   ├── test_application.py
│   ├── test_milvus_integration.py
│   ├── test_services.py
│   ├── test_api.py
│   └── *.txt
├── evaluation/
│   ├── __init__.py
│   ├── adapters.py
│   ├── integration.py
│   ├── fingerprints.py
│   ├── production.py
│   ├── production_runner.py
│   ├── comparison.py
│   ├── comparison_runner.py
│   ├── rewrite_artifacts.py
│   ├── rewrite_runner.py
│   ├── metrics.py
│   ├── models.py
│   ├── regression.py
│   ├── regression_runner.py
│   ├── reports.py
│   ├── runner.py
│   ├── datasets/
│   │   ├── golden_dataset.jsonl
│   │   ├── documents/
│   │   ├── v1_6/
│   │       ├── golden_dataset.jsonl
│   │       ├── holdout_dataset.jsonl
│   │       └── documents/
│   │   └── v1_7/                # 经数据集指纹绑定的 Rewrite artifact
│   ├── baselines/
│   └── reports/
├── frontend/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api.ts
│   │   ├── api.test.ts
│   │   ├── conversations.ts
│   │   ├── conversations.test.ts
│   │   ├── types.ts
│   │   └── styles.css
│   ├── e2e/
│   │   ├── mock-api.mjs
│   │   └── workbench.spec.ts
│   ├── playwright.config.ts
│   ├── vite.config.ts
│   ├── package.json
│   └── package-lock.json
├── infra/
│   └── milvus/
│       └── compose.yaml
├── .github/
│   └── workflows/
│       └── ci.yml
├── data/                  # 本地运行数据，Git 忽略
├── logs/                  # JSONL 日志，Git 忽略
├── .env                   # 本地密钥，Git 忽略
├── .env.example           # 无密钥配置模板
├── .dockerignore
├── .gitignore
├── compose.yaml
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── ARCHITECTURE.md
├── DEMO_SCRIPT.md
├── DEPENDENCIES.md
├── OBSERVABILITY.md
├── EVALUATION.md
├── PROJECT_STRUCTURE.md
├── VERSION_HISTORY.md
└── web_app.py
```

## 模块职责

| 文件 | 职责 |
|---|---|
| `app/config.py` | 环境变量加载、默认值和参数验证 |
| `document_loader.py` | PDF/DOCX/TXT 加载、稳定文档 ID、页码元数据 |
| `document_chunker.py` | 文档分块、稳定 Chunk ID、空块过滤 |
| `embedding_client.py` | Ollama 和 API Embedding 统一调用 |
| `vector_store.py` | Milvus Collection、upsert、search、delete 和 Embedding 空间校验 |
| `retriever.py` | Dense 检索、BM25 中文/标识符分词、RRF、多查询融合、重排编排和结果分数契约 |
| `query_rewriter.py` | 原问题保留、规范化去重、严格 JSON LLM 改写和确定性映射 |
| `reranker.py` | 延迟加载 Cross-Encoder，扩大候选后赋予独立 `rerank_score` |
| `generator.py` | OpenAI 兼容/Anthropic 消息适配和流式生成 |
| `web_app.py` | 上传校验、生命周期服务调用、问答编排、根 Span、Metrics 服务和 UI |
| `app/services/rag_service.py` | 将检索和生成编排为 `status/sources/token/done/error` 结构化事件 |
| `app/services/document_service.py` | 文档摄取、列表、详情、重建和可恢复删除编排 |
| `app/api/main.py` | FastAPI 应用工厂、生命周期初始化、CORS、Request ID 和异常处理 |
| `app/api/schemas.py` | 健康、配置、文档详情/删除、上传和聊天请求/响应模型 |
| `app/api/routers/*.py` | health、system、documents、chat HTTP 路由 |
| `app/api/sse.py` | 将结构化 ChatEvent 编码为 SSE 帧 |
| `frontend/src/App.tsx` | React 工作台状态、问答流、文档管理、上传阶段、来源抽屉和本地历史 |
| `frontend/src/api.ts` | REST/XHR 请求、上传进度、错误映射和 SSE 流解析 |
| `frontend/src/conversations.ts` | 对话标题、数量限制、`localStorage` 读取/校验/持久化 |
| `frontend/e2e/mock-api.mjs` | 可控状态的本地 HTTP API，用于无真实 Provider 的浏览器回归 |
| `frontend/e2e/workbench.spec.ts` | 服务恢复、上传、文档管理、流式问答、停止生成和历史管理 E2E |
| `compose.yaml` | 编排 FastAPI、React、Milvus、etcd、MinIO，定义健康依赖、端口和持久卷 |
| `Dockerfile` | Python 3.11 后端镜像入口，安装运行依赖并启动 `python -m app.api` |
| `frontend/Dockerfile` | Node 22 前端构建与 `vite preview` 演示服务入口 |
| `.dockerignore` / `frontend/.dockerignore` | 排除密钥、运行数据、缓存、依赖目录和测试产物 |
| `.github/workflows/ci.yml` | Python、前端、Playwright 和 Compose 配置的自动回归门禁 |
| `infra/milvus/compose.yaml` | Milvus Standalone、etcd、MinIO、健康检查和本地持久卷 |
| `VERSION_HISTORY.md` | 版本边界、逐提交事实与发布验收记录 |
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
| `evaluation/adapters.py` | Dense、BM25、Hybrid、Rewrite、Rerank 适配器与离线 Fake Adapter |
| `evaluation/integration.py` | 确定性 Embedding、内存 Vector Store 和三种检索模式集成烟囱测试 |
| `evaluation/fingerprints.py` | 黄金数据集和评估文档语料的稳定 SHA-256 指纹 |
| `evaluation/production.py` | Dense、BM25、Hybrid 和 v1.7 实验组件评估装配 |
| `evaluation/production_runner.py` | 真实 Provider 基线、Rewrite、Rerank 实验 CLI |
| `evaluation/comparison.py` | 四种增强模式的同配置校验、质量/延迟矩阵和基线差值 |
| `evaluation/comparison_runner.py` | 生成 v1.7.1 四模式 JSON/Markdown 对照报告的 CLI |
| `evaluation/rewrite_artifacts.py` | 严格 Rewrite artifact 生成、读取和数据集指纹校验 |
| `evaluation/rewrite_runner.py` | 通过 LLM 生成可复现 Rewrite artifact 的 CLI |
| `evaluation/runner.py` | JSONL 黄金评估集加载、分类汇总、延迟分位数和确定性三模式执行 |
| `evaluation/regression.py` | 报告输入兼容性、指标最低值和允许下降幅度门禁 |
| `evaluation/regression_runner.py` | 报告兼容性校验和自动回归门禁 CLI |
| `evaluation/reports.py` | JSON/Markdown 报告文件输出 |

## 依赖方向

```text
frontend/src/api.ts
    └── FastAPI /api/v1
        ├── app.api.routers.*
        ├── app.services.*
        ├── app.config
        ├── app.core.*
        ├── app.lifecycle.*
        └── app.observability.*

python -m app.api
    └── uvicorn → app.api.main:app

app.lifecycle.service
├── app.core.document_loader
├── app.core.document_chunker
├── app.core.vector_store
└── app.lifecycle.registry

app.core.retriever
├── app.observability.metrics
└── app.observability.tracing
```

React 工作台通过 `frontend/src/api.ts` 访问 FastAPI，不直接导入 Python 模块；SSE 事件由 `app/api/sse.py` 编码，由 `app/services/rag_service.py` 统一产生。浏览器对话历史通过 `frontend/src/conversations.ts` 独立保存，不进入 API。`web_app.py` 仍保留为兼容入口。

可观测性模块不得反向导入 Web UI 或具体 RAG 组件，避免循环依赖。

## 运行数据边界

以下目录不得提交到 Git：

- Milvus 服务端数据目录（不属于本仓库）
- `data/uploads/`
- `data/document_registry.sqlite3`
- `logs/`
- `venv/`
- `__pycache__/`
- `.env`
