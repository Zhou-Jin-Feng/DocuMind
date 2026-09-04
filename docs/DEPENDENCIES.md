# 依赖说明（v2.2.0）

## Python 运行依赖

| 分类 | 依赖 | 用途 |
|---|---|---|
| LangChain | `langchain`、`langchain-core` | `Document` 数据结构与基础抽象 |
| LangChain | `langchain-community`、`langchain-text-splitters` | PDF/DOCX/TXT Loader 和文本分块 |
| LangChain | `langchain-openai` | OpenAI 兼容的 LangChain 集成 |
| Embedding | `langchain-ollama` | 本地 Ollama Embedding |
| Reranker | `sentence-transformers` | Cross-Encoder 候选重排；模型按需加载 |
| Vector DB | `pymilvus` | 连接 Milvus Standalone 并管理向量索引 |
| LLM | `openai` | OpenAI、DeepSeek、GLM 兼容客户端 |
| LLM | `anthropic` | Claude 客户端 |
| Documents | `pypdf`、`python-docx`、`docx2txt` | PDF 和 DOCX 文本处理 |
| Web API | `fastapi`、`uvicorn[standard]`、`python-multipart` | 主 API 入口、ASGI 服务和文件上传 |
| 兼容界面 | `gradio` | 保留的 `web_app.py` 兼容入口，不是主交付界面 |
| Config | `pydantic`、`pydantic-settings`、`python-dotenv` | 模型、`.env` 加载和配置验证 |
| Retrieval | `numpy`、`rank-bm25`、`jieba` | 向量计算、BM25 和中文/标识符分词 |
| HTTP | `httpx`、`requests` | Provider 请求和 API 测试支持 |
| Logging | `loguru` | 结构化控制台和 JSONL 文件日志 |
| Metrics | `prometheus-client` | Counter、Histogram 和 Metrics HTTP 服务 |
| Tracing | `opentelemetry-api` | Trace API、Span 和上下文接口 |
| Tracing | `opentelemetry-sdk` | 私有 TracerProvider、Resource 和 SpanProcessor |
| Tracing | `opentelemetry-exporter-otlp-proto-http` | 可选 OTLP/HTTP Trace 导出 |
| Utilities | `tiktoken`, `rich` | 分块分析和终端展示 |

`requirements.txt` 只声明 Python 直接依赖，不等同于完整锁文件。`sentence-transformers` 会带入 PyTorch、Transformers 和 SciPy 等运行依赖；普通 Dense/BM25/Hybrid 链路不会加载重排模型。

## 前端依赖

`frontend/package.json` 使用 React 19、TanStack Query、React Markdown、Remark GFM 和 Lucide React 构建工作台。TypeScript、Vite、Vitest 和 Playwright 属于前端开发/验证依赖。

`frontend/package-lock.json` 是当前前端锁文件；本地和 CI 都应使用 `npm ci`，避免绕过已提交的依赖树。

## 外部运行服务

- Milvus Standalone 是必需向量数据库；etcd 和 MinIO 由 Compose 一同编排。
- 默认 Embedding 使用宿主机 Ollama `qwen3-embedding`，Compose 不会自动安装或启动 Ollama；
  `OLLAMA_EMBEDDING_KEEP_ALIVE_SECONDS` 默认设为 600 秒（范围 `0-3600`），用于降低连续
  检索的冷启动概率；`OLLAMA_EMBEDDING_READINESS_TIMEOUT_SECONDS` 默认允许 60 秒的有界
  冷加载。两项都不能视为永久驻留或 GPU 容量保证。
- 回答生成需要已配置的 OpenAI、Anthropic、DeepSeek 或 GLM Provider。
- Prometheus、Grafana、Jaeger 和 OpenTelemetry Collector 不在当前 Compose 内；应用仅暴露 Metrics 并可选向外部 OTLP/HTTP endpoint 导出 Trace。

## 可观测性依赖边界

- `prometheus-client` 在内存中维护指标；只有主入口调用 `start_metrics_server()` 后才监听端口。
- OpenTelemetry API/SDK 可在无 Collector 的情况下运行。
- OTLP/HTTP Exporter 只有在 `TRACING_ENABLED=true` 且 endpoint 非空时才创建，并通过 `BatchSpanProcessor` 批量导出。
- 测试使用 `InMemorySpanExporter`，不会访问网络。
- 本版本没有引入 Prometheus、Grafana、Jaeger 或 Collector 服务端依赖。

## 安装

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

开发依赖：

```powershell
pip install -r requirements-dev.txt
```

`requirements-dev.txt` 已通过 `-r requirements.txt` 包含核心依赖，无需重复执行两次安装命令。

前端依赖：

```powershell
Set-Location frontend
npm ci
```

统一 Compose 交付使用 `python:3.11-slim` 和 `node:22-alpine` 作为默认基础镜像，完整启动步骤见根目录 `README.md`。

## 验证

```powershell
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP documind_pycache
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\venv\Scripts\python.exe -m compileall -q app web_app.py tests
.\venv\Scripts\python.exe -m compileall -q evaluation
Set-Location frontend
npm test
npm run typecheck
npm run build
```

## 可复现性说明

前端已有 npm 锁文件，Python 依赖仍未锁定具体版本。Dockerfile 固定基础镜像主版本，但不等同于 Python 依赖锁定或镜像 digest 锁定。Rewrite artifact 记录 LLM、模型、最大改写数和数据集 SHA-256；Rerank 报告记录 sentence-transformers 模型和本地缓存模式。若需要严格可复现部署，后续应生成并验证 Python 锁文件，同时记录底层模型和容器镜像版本。
