# 可观测性指南（v2.0.2）

Logs + Metrics + Traces 能力最初在 v1.3 引入，当前由 FastAPI 主入口和保留的 Gradio 兼容入口共用。应用实现内部埋点、Metrics HTTP 端口和可选 OTLP/HTTP Trace 导出；Prometheus、Grafana、Jaeger 和 OpenTelemetry Collector 等外部后端不在当前 Compose 内。

## 1. 设计目标

- 同一次上传或问答使用一个 `request_id`，便于串联完整日志。
- Tracing 开启时，日志中的 `trace_id` 与 OpenTelemetry Span Trace ID 一致。
- 所有耗时使用 `time.perf_counter()`，日志单位为数字毫秒，Metrics 单位为秒。
- Metrics 标签只使用低基数字段，禁止把问题、文件名和请求标识作为标签。
- 默认不记录问题全文、文档正文、API Key、Bearer Token 或完整异常消息。
- 模块导入不监听端口、不创建日志文件、不发送网络请求。

## 2. 结构化日志

### 2.1 默认输出

- 控制台：开发友好的文本格式。
- 文件：`./logs/rag_{time:YYYY-MM-DD}.jsonl`，每行一个扁平 JSON 对象。
- 日志目录只在 `setup_logger()` 被应用入口显式调用后创建。

### 2.2 标准字段

| 字段 | 说明 |
|---|---|
| `service` | 服务名，默认 `rag-web` |
| `environment` | 环境名，默认 `development` |
| `event` | 稳定事件名，例如 `retrieval_completed` |
| `operation` | 操作名，例如 `rag.retrieve` |
| `request_id` | 一次业务请求内保持一致 |
| `trace_id` | Tracing 开启时与 Span Trace ID 一致 |
| `duration_ms` | 数字毫秒，不使用带单位字符串 |
| `status` | `started`、`success`、`no_context`、`rejected` 或 `error` |
| `error_type` | 只记录异常类型，不把异常消息作为结构化字段 |

### 2.3 问答事件顺序

```text
query_received
→ retrieval_started
→ query_embedding_completed
→ retrieval_completed
→ context_built
→ generation_started
→ first_token_received
→ generation_completed
→ response_sent
```

异常时会出现 `query_embedding_failed`、`vector_search_failed`、`retrieval_failed`、`llm_stream_failed`、`generation_completed(status=error)` 或 `response_sent(status=error)`。

FastAPI 中间件会验证或生成 `X-Request-ID`，把它写入请求上下文并在响应头中返回。SSE 问答由服务层产生结构化事件，已发送部分 Token 后如果 Provider 中断，前端保留已收到文本并显示错误状态。Gradio 兼容入口另外使用固定 `contextvars.Context` 保持整个流生命周期内的 `request_id` / `trace_id`。

### 2.4 文档摄取事件顺序

```text
document_upload_received
→ document_loaded
→ document_chunked
→ document_embedding_completed
→ vector_upsert_completed
→ document_indexing_completed
```

日志只记录扩展名、文件大小、文档数、Chunk 数和集合数量，不记录上传文件名和文档正文。

## 3. Prometheus Metrics

### 3.1 配置

```dotenv
METRICS_ENABLED=true
METRICS_HOST=127.0.0.1
METRICS_PORT=8000
```

Web 主入口会显式启动 Metrics HTTP 服务。默认地址为 `http://127.0.0.1:8000/metrics`。将 `METRICS_ENABLED=false` 后，所有指标调用透明退化为 no-op，且不会监听端口。

### 3.2 指标清单

| 指标 | 类型 | 用途 |
|---|---|---|
| `rag_queries_total` | Counter | 问答请求结果计数 |
| `rag_query_duration_seconds` | Histogram | 问答总耗时 |
| `rag_no_context_total` | Counter | 无可用上下文次数 |
| `rag_component_errors_total` | Counter | 组件异常计数 |
| `rag_documents_uploaded_total` | Counter | 上传接收或拒绝计数 |
| `rag_document_ingestion_duration_seconds` | Histogram | 文档摄取总耗时 |
| `rag_chunks_created_total` | Counter | 创建 Chunk 数 |
| `rag_chunks_indexed_total` | Counter | 写入索引 Chunk 数 |
| `rag_embedding_duration_seconds` | Histogram | Query/Batch Embedding 耗时 |
| `rag_retrieval_duration_seconds` | Histogram | 检索耗时 |
| `rag_retrieval_result_count` | Histogram | 检索结果数量 |
| `rag_llm_first_token_duration_seconds` | Histogram | 首 Token 延迟 |
| `rag_llm_total_duration_seconds` | Histogram | LLM 流式生成总耗时 |

允许的标签只有：`provider`、`operation`、`status`、`error_type`。禁止使用 `request_id`、`trace_id`、问题、文件名、文档 ID 或 API Key 作为指标标签。

### 3.3 本地检查

启动应用后执行：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/metrics | Select-Object -ExpandProperty Content
```

## 4. OpenTelemetry Tracing

### 4.1 默认关闭

```dotenv
TRACING_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=
```

- 关闭时 `trace_span()` 是 no-op，不影响 RAG 流程。
- 开启但 endpoint 为空时，只创建应用私有 SDK Provider，不创建网络导出器。
- 配置 endpoint 后才创建 OTLP/HTTP Trace Exporter，并使用 `BatchSpanProcessor` 避免在业务请求内同步逐条导出。常见 Collector 地址为 `http://127.0.0.1:4318/v1/traces`。
- 应用不会调用 `trace.set_tracer_provider()`，因此不会覆盖依赖库或宿主进程的全局 Provider。

### 4.2 Span 树

问答：

```text
rag.query
├── rag.retrieve
│   ├── embedding.query
│   └── vector.search
├── rag.context.build
└── llm.generate
```

文档摄取：

```text
rag.document.ingest
├── document.load
├── document.chunk
├── embedding.batch
└── vector.upsert
```

### 4.3 错误与隐私

- 错误 Span 设置 `StatusCode.ERROR`。
- 错误属性仅补充 `error.type`；禁用 OpenTelemetry 默认异常事件，避免把完整异常消息和堆栈发送到外部系统。
- Span 属性过滤问题正文、Prompt、文件名、文档正文、凭据、`request_id`、`trace_id` 和 `document_id`。
- 日志仍在本地记录异常堆栈，但统一脱敏，并且 UI 只返回通用错误。

## 5. 配置速查

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `SERVICE_NAME` | `rag-web` | 日志和 Trace Resource 的服务名 |
| `APP_ENV` | `development` | 环境名 |
| `LOG_CONSOLE_FORMAT` | `text` | 控制台 `text` 或 `json` |
| `LOG_FILE_FORMAT` | `json` | 文件 `text` 或 `json` |
| `METRICS_ENABLED` | `true` | 是否启用 Prometheus 指标 |
| `METRICS_HOST` | `127.0.0.1` | Metrics 监听地址 |
| `METRICS_PORT` | `8000` | Metrics 端口 |
| `TRACING_ENABLED` | `false` | 是否启用 OpenTelemetry Span |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 空 | OTLP/HTTP Trace 接收地址 |

## 6. 离线安全模式

测试、演示或没有 Collector 时可使用：

```dotenv
METRICS_ENABLED=false
TRACING_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=
```

该模式不监听 Metrics 端口、不创建 OTLP 导出器，也不要求真实 Prometheus 或 Trace 后端。结构化日志仍可写入本地临时路径。

## 7. 验证命令

```powershell
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP documind_pycache
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m compileall -q app web_app.py tests
.\venv\Scripts\python.exe -m pip check
git diff --check
```

## 8. 当前范围边界

当前仓库已包含 Docker Compose、文档生命周期、黄金评测集以及 Query Rewrite/Reranker 离线实验能力。可观测性边界仍是单实例应用端埋点：不部署 Prometheus/Grafana/Jaeger/Collector，不提供告警规则、长期指标存储或分布式 Trace 运维保证。认证、多租户、Celery/Redis 和生产高可用同样不在当前范围内。
