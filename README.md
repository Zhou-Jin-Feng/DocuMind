# DocuMind - RAG 知识库问答系统（v1.5）

这是一个采用 Python Package 分层结构的本地单用户 RAG 本地单用户项目，支持文档加载、稳定分块、向量索引、语义检索、流式生成、来源展示，以及结构化日志、Prometheus Metrics、OpenTelemetry Tracing、离线 RAG 评估和文档生命周期管理。

> 当前版本：**v1.5 文档生命周期版**。本版本在 v1.4 评估门禁的基础上增加文档注册表、索引清单、active 版本切换、失败恢复和运维 CLI。Docker/Compose、混合检索和异步任务仍按后续版本推进。

## 当前能力

- 支持 PDF、DOCX、TXT 文档；不支持旧版 `.doc`。
- 文档和 Chunk 使用稳定 ID，相同内容重复上传是 no-op，内容更新会生成新版本并在构建成功后切换 active 索引。
- SQLite 文档注册表保存源文件哈希、版本、索引清单、操作进度和错误状态；Chroma 只保存向量。
- 提供 `list`、`audit`、`cleanup`、`rebuild` 生命周期 CLI，支持 `rebuild --dry-run`。
- 检索结果明确使用 **distance（距离，越小越相关）**，并支持最大距离阈值。
- PDF 页面统一显示为从 1 开始的页码。
- OpenAI、Anthropic Claude、DeepSeek、GLM 生成接口，以及 Ollama/OpenAI 兼容 Embedding。
- 上传扩展名、上传大小、分块、检索和 LLM 参数统一从 `app/config.py` 与 `.env` 读取。
- 默认 Web 服务和 Metrics 服务都只监听 `127.0.0.1`。
- JSONL 结构化日志内置 `request_id` / `trace_id`、阶段事件、数字毫秒耗时和敏感字段脱敏。
- Prometheus Metrics 使用低基数标签，默认暴露在 `127.0.0.1:8000/metrics`。
- OpenTelemetry Tracing 默认关闭，支持应用私有 Provider、OTLP/HTTP 导出和日志 Trace ID 关联。
- 提供离线黄金评估集、Recall@K、Precision@K、MRR、Top-K 命中率、拒答准确率和回归门禁。

## 项目结构

```text
DocuMind/
├── app/
│   ├── config.py                 # Pydantic Settings 配置
│   ├── core/
│   │   ├── document_loader.py    # PDF/DOCX/TXT 加载与文档元数据
│   │   ├── document_chunker.py   # 分块与稳定 Chunk ID
│   │   ├── embedding_client.py   # 多 Provider Embedding
│   │   ├── vector_store.py       # Chroma upsert/search/delete
│   │   ├── retriever.py          # 距离阈值与轻量重排
│   │   └── generator.py          # 多 Provider 流式生成
│   ├── observability/
│   │   ├── context.py            # request_id / trace_id 上下文
│   │   ├── logging.py            # JSONL 结构化日志与脱敏
│   │   ├── metrics.py            # Prometheus 指标与显式服务启动
│   │   └── tracing.py            # OpenTelemetry Span 与 OTLP 导出
│   ├── lifecycle/
│   │   ├── models.py             # 文档、版本、索引和审计数据模型
│   │   ├── registry.py           # SQLite 生命周期注册表
│   │   ├── service.py            # 同步构建、切换、清理和重建
│   │   ├── cli.py                # list/audit/cleanup/rebuild CLI
│   │   └── __main__.py           # python -m app.lifecycle
│   └── utils/
│       ├── logger.py             # 日志兼容入口
│       └── monitoring.py         # 生成器安全的耗时工具
├── tests/                        # unittest 自动化测试和示例文本
├── evaluation/                   # 黄金评估集、离线 Runner、报告和回归门禁
│   ├── datasets/
│   ├── baselines/
│   ├── reports/
│   └── runner.py
├── data/                         # 运行数据（Git 忽略）
├── logs/                         # 日志（Git 忽略）
├── .env.example                 # 无密钥配置模板
├── requirements.txt
├── requirements-dev.txt
├── OBSERVABILITY.md              # v1.3 日志、指标、追踪指南
├── EVALUATION.md                 # v1.4 黄金评估集和回归评估指南
└── web_app.py                    # Gradio 入口
```

## 环境要求

- Windows PowerShell（以下命令以 Windows 为例）
- Python 3.11 或更高版本
- 至少配置一个 LLM Provider
- 默认 Embedding 使用本地 Ollama，需要 Ollama 服务和对应模型

## 快速开始

### 1. 创建并激活虚拟环境

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

若需要测试与代码质量工具：

```powershell
pip install -r requirements-dev.txt
```

### 3. 创建配置文件

```powershell
Copy-Item .env.example .env
```

不要把真实 API Key 写入 `.env.example`，也不要提交 `.env`。

### 4. 准备 Provider

默认 Embedding Provider 是 Ollama：

```powershell
ollama serve
ollama pull qwen3-embedding
```

然后在 `.env` 中为所选 LLM 填写 API Key。例如使用 OpenAI 时填写：

```dotenv
DEFAULT_LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key
```

### 5. 启动 Web 应用

```powershell
python web_app.py
```

默认访问地址：`http://127.0.0.1:7860`。

### 6. 生命周期运维命令

生命周期命令不需要启动 Web 服务。`list`、`audit`、`cleanup` 和 `rebuild --dry-run` 不会连接 Embedding Provider；实际重建才会初始化当前配置的 Provider。

```powershell
python -m app.lifecycle list
python -m app.lifecycle audit
python -m app.lifecycle cleanup --dry-run
python -m app.lifecycle cleanup --include-orphans
python -m app.lifecycle rebuild --document-key <document_key> --dry-run
python -m app.lifecycle rebuild --document-key <document_key>
python -m app.lifecycle rebuild --document-key <document_key> --retry
```

命令支持 `--json` 输出，便于脚本和后续任务系统接入。`audit` 同时检查 active 缺失与 Chunk 数不一致；`cleanup` 默认只处理注册表中的旧版本，并可恢复中断在 `deleting` 的清理。确认需要处理整个 Chroma Collection 中未注册的索引时再加 `--include-orphans`。

`rebuild --dry-run` 会校验持久化源文件哈希，并按当前 Chunk/Embedding 配置计算 planned `index_id` 和 `configuration_changed`；Provider/模型未变化时复用上次成功索引验证过的真实维度，源文件缺失或被篡改时直接报错。

`rebuild --retry` 只回收指定文档下唯一的中断 `indexing` 目标，包括尚未切换 active 的新版本。若没有中断目标、同时存在多个目标，或当前配置已无法生成原 `index_id`，命令会拒绝执行并给出错误。

## 关键配置

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `CHUNK_SIZE` | `500` | Chunk 字符长度 |
| `CHUNK_OVERLAP` | `100` | Chunk 重叠长度，必须小于 `CHUNK_SIZE` |
| `RETRIEVAL_TOP_K` | `3` | 返回候选数量 |
| `RETRIEVAL_SCORE_THRESHOLD` | 空 | Chroma 最大距离；越小越严格 |
| `LLM_TEMPERATURE` | `0.7` | 生成温度，范围 0–2 |
| `LLM_MAX_TOKENS` | `1000` | 最大生成 Token 数 |
| `MAX_UPLOAD_SIZE_MB` | `50` | 上传大小限制 |
| `DOCUMENT_REGISTRY_PATH` | `./data/document_registry.sqlite3` | 文档生命周期 SQLite 注册表 |
| `DEFAULT_TENANT_ID` | `default` | 当前本地运行上下文的租户命名空间 |
| `DEFAULT_USER_ID` | `local-user` | 当前本地运行上下文的用户占位标识 |
| `SERVER_HOST` | `127.0.0.1` | 无认证时不要改为公网监听 |
| `LOG_FILE_FORMAT` | `json` | 文件日志格式，推荐 JSONL |
| `METRICS_ENABLED` | `true` | 是否启用 Prometheus Metrics |
| `METRICS_HOST` | `127.0.0.1` | Metrics 默认只监听本机 |
| `METRICS_PORT` | `8000` | Metrics HTTP 端口 |
| `TRACING_ENABLED` | `false` | 是否启用 OpenTelemetry Tracing |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 空 | OTLP/HTTP Trace 地址 |

`ALLOWED_EXTENSIONS` 是 JSON 数组，例如：

```dotenv
ALLOWED_EXTENSIONS=[".pdf", ".docx", ".txt"]
```

## 可观测性

- 结构化文件日志：`logs/rag_YYYY-MM-DD.jsonl`。
- Metrics：启动应用后访问 `http://127.0.0.1:8000/metrics`。
- Tracing：设置 `TRACING_ENABLED=true` 后创建 Span；只有同时配置 `OTEL_EXPORTER_OTLP_ENDPOINT` 才会向 OTLP/HTTP 后端导出。
- 离线测试时可同时设置 `METRICS_ENABLED=false` 和 `TRACING_ENABLED=false`，不会监听端口或发送 Trace。

字段、事件顺序、指标清单、Span 树与隐私约束见 [OBSERVABILITY.md](OBSERVABILITY.md)。

## RAG 评估

离线运行默认黄金评估集，不需要 Ollama、ChromaDB、网络或真实 LLM：

```powershell
python -m evaluation.runner `
  --dataset evaluation/datasets/golden_dataset.jsonl `
  --output-json evaluation/reports/demo.json `
  --output-markdown evaluation/reports/demo.md
```

数据格式、指标语义、Adapter 接入方式和回归门禁见 [EVALUATION.md](EVALUATION.md)。

## 测试与检查

项目测试使用标准库 `unittest`，不依赖 pytest 也可运行：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m compileall -q app evaluation web_app.py tests
python -m pip check
```

## 数据和索引

- Chroma 默认目录：`data/chroma_db/`
- 文档注册表：`data/document_registry.sqlite3`
- 上传源文件持久化目录：`data/uploads/`（按内容哈希命名，已加入 Git 忽略）
- 日志目录：`logs/`
- 上述运行数据均应保持在 Git 之外。

相同文件名且内容完全相同的文档会得到相同 `document_key`、`document_version_id`、`index_id` 和 `chunk_id`，健康索引的重复上传不会增加 Chunk。如果 active 向量缺失或数量不一致，重复上传会自动进入修复构建。内容更新会先构建新索引，成功后才切换 active；失败时旧 active 仍可检索。

### 清空并重建本地索引

先停止 Web 服务，再执行：

```powershell
Remove-Item -Recurse -Force .\data\chroma_db
Remove-Item -Force .\data\document_registry.sqlite3
```

优先使用生命周期命令清理和重建。只有需要丢弃全部本地数据时才删除整个 Chroma 目录和 `data/document_registry.sqlite3`，再重新上传文档。

## 已知限制

- 对话历史目前只用于 UI 展示，尚未参与 Query Rewrite 或历史感知检索。
- v1.4 之前写入的旧向量没有 `index_id`，当前检索会兼容保留；`audit` 会报告 legacy Chunk，后续可安排显式迁移。
- 首次接管无 Embedding 元数据的非空 v1.4 Collection 时，只能核对实际向量维度，并假定它由当前 Provider/模型生成；旧数据本身无法反推出模型身份。
- 非空 Collection 禁止切换 Embedding Provider、模型或维度；v1.5 不提供跨向量空间的在线 shadow migration，更换模型需使用新 Collection 或清空后全量重建。
- 当前是同步生命周期流程；Celery/Redis 异步摄取、认证和多租户授权属于 v2.0/v2.1。
- 目前是本地单用户应用，没有认证、租户隔离和生产级限流。
- 当前仍只提供应用内 Metrics 和可选 OTLP Trace 导出；Prometheus、Grafana、Jaeger 与 Collector 的部署不属于 v1.5。

## 常见问题

### 系统初始化失败

检查：

1. `.env` 中选定的 Provider 是否有 API Key；
2. Ollama 是否正在运行，Embedding 模型是否已下载；
3. `pip check` 是否通过；
4. `logs/` 中是否有完整异常。

### 上传后没有结果

- 确认文档有可提取文本；扫描版 PDF 暂不包含 OCR。
- 如果配置了 `RETRIEVAL_SCORE_THRESHOLD`，可适当调大或暂时留空。
- “系统错误”和“无检索结果”已分开处理，系统错误请查看日志。

### 更换 Embedding 模型后查询失败

系统会在写入和查询前校验 Collection 保存的 Embedding Provider、模型、维度及实际向量维度，同维度的不同模型也会被拒绝，避免语义空间静默混用。停止服务后改用新的 `COLLECTION_NAME` 并全量重建；确认旧索引无需保留时，也可以同时清空 Chroma 和生命周期注册表后重新上传。
