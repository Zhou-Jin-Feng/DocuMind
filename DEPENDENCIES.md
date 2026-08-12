# 依赖说明（v1.7）

## 核心直接依赖

| 分类 | 依赖 | 用途 |
|---|---|---|
| LangChain | `langchain-core` | `Document` 数据结构 |
| LangChain | `langchain-community` | PDF、DOCX、TXT Loader |
| LangChain | `langchain-text-splitters` | 字符和递归分块 |
| Embedding | `langchain-ollama` | 本地 Ollama Embedding |
| Reranker | `sentence-transformers` | Cross-Encoder 候选重排；模型按需加载 |
| Vector DB | `pymilvus` | 连接 Milvus Standalone 并管理向量索引 |
| LLM | `openai` | OpenAI、DeepSeek、GLM 兼容客户端 |
| LLM | `anthropic` | Claude 客户端 |
| Documents | `pypdf` | PDF 文本提取 |
| Documents | `docx2txt` | `Docx2txtLoader` 的直接运行依赖 |
| Web | `gradio` | Web UI |
| Config | `pydantic-settings` | `.env` 和配置验证 |
| Logging | `loguru` | 结构化控制台和 JSONL 文件日志 |
| Metrics | `prometheus-client` | Counter、Histogram 和 Metrics HTTP 服务 |
| Tracing | `opentelemetry-api` | Trace API、Span 和上下文接口 |
| Tracing | `opentelemetry-sdk` | 私有 TracerProvider、Resource 和 SpanProcessor |
| Tracing | `opentelemetry-exporter-otlp-proto-http` | 可选 OTLP/HTTP Trace 导出 |
| Utilities | `tiktoken`, `rich` | 分块分析和终端展示 |

`requirements.txt` 只声明直接依赖，不等同于完整锁文件。`sentence-transformers` 会带入 PyTorch、Transformers 和 SciPy 等运行依赖；普通 Dense/BM25/Hybrid 链路不会加载重排模型。

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

## 验证

```powershell
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP documind_pycache
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\venv\Scripts\python.exe -m compileall -q app web_app.py tests
.\venv\Scripts\python.exe -m compileall -q evaluation
```

## 可复现性说明

当前仓库尚未引入锁文件。Rewrite artifact 记录 LLM、模型、最大改写数和数据集 SHA-256；Rerank 报告记录 sentence-transformers 模型和本地缓存模式。若后续需要严格可复现部署，按既定计划在 Docker 阶段确定 Python 基础镜像后，再生成并验证锁文件。
