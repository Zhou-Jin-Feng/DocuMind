# DocuMind - RAG 知识库问答系统（v2.0）

这是一个采用 Python Package 分层结构的本地单用户 RAG 本地单用户项目，支持文档加载、稳定分块、向量索引、语义检索、词法检索实验、流式生成、来源展示，以及结构化日志、Prometheus Metrics、OpenTelemetry Tracing、离线 RAG 评估和文档生命周期管理。

> 当前版本：**v2.0 收尾交付版（应用版本 `2.0.0`）**。默认链路为 FastAPI + React/TypeScript + Milvus Standalone，支持 SSE 流式问答、完整文档管理、真实依赖探活、引用来源、上传阶段反馈和本地对话历史，并提供统一 Docker Compose、前后端镜像入口、CI 门禁和演示脚本。Gradio 入口仅作为兼容与回归入口保留。

## 当前能力

- 支持 PDF、DOCX、TXT 文档；不支持旧版 `.doc`。
- 文档和 Chunk 使用稳定 ID，相同内容重复上传是 no-op，内容更新会生成新版本并在构建成功后切换 active 索引。
- SQLite 文档注册表保存源文件哈希、版本、索引清单、操作进度和错误状态；Milvus Standalone 保存向量及检索元数据。
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
- v1.6 评估集包含 32 条原始用例和 12 条独立 holdout，用例按类别与 split 分别输出指标。
- 提供中文/英文标识符 BM25 检索，以及可配置权重、RRF 常数和候选深度的混合检索实验入口。
- Dense 最大距离和 BM25 最低词法分数可独立校准，并写入评估报告元数据。
- v1.7 评估链路始终保留原问题，按稳定 `chunk_id` 融合多条查询，并在扩大候选集后记录独立 `rerank_score`；原始 distance、词法和 RRF 分数不会被覆盖。
- v1.7.1 固化 Rewrite artifact 的 schema/Prompt/生成参数指纹，增加断点续跑、延迟分位数、严格四模式比较，并按唯一文档 ID 计算 Precision@K。
- v1.8 完成 Chroma 到 Milvus 的向量存储迁移，并保留 Embedding 空间、维度和 Collection 兼容性校验。
- v1.9 搭建 FastAPI 后端与 React/TypeScript 前端：统一错误响应、健康检查、公开配置、文档接口、SSE 问答和前端服务状态反馈。
- v1.9.1 完成真实 RAG 闭环、Milvus/Ollama 探活、前端 E2E、文档详情/重建/删除、上传进度和本地对话历史。
- v2.0 完成 FastAPI、React、Milvus、etcd、MinIO 统一 Compose，补齐前后端容器入口、GitHub Actions CI、回归口径和交付演示材料。

## 版本迭代记录

README 保留面向仓库用户的公开版本摘要；当前架构边界见 [ARCHITECTURE.md](ARCHITECTURE.md)，评估指标、报告和质量门禁见 [EVALUATION.md](EVALUATION.md)，逐版本和逐提交说明见 [VERSION_HISTORY.md](VERSION_HISTORY.md)。本地设计草稿仍由 `.gitignore` 排除。

| 版本 | 迭代内容 |
|---|---|
| v1.0 | 初始 RAG 原型：文档加载、向量索引、检索和生成 |
| v1.2 | 项目分层、依赖整理和基础稳定性修正 |
| v1.3 | 结构化日志、Prometheus Metrics 和 OpenTelemetry Tracing |
| v1.4 | 黄金评估集、真实 Provider 验证和回归门禁 |
| v1.5 | 文档注册表、索引生命周期、active 切换和失败恢复 |
| v1.6 | Dense、BM25、Hybrid/RRF 检索质量对照 |
| v1.6.1 | 真实 Ollama holdout、阈值/RRF 校准和质量门禁 |
| v1.7 | 严格 Query Rewrite artifact、多查询 RRF 和 Cross-Encoder Reranker 评估实验 |
| v1.7.1 | 可复现 Rewrite artifact、四模式同配置比较、延迟分位数和指标口径修正 |
| v1.8 | Chroma 到 Milvus 的向量数据迁移与运行时兼容性校验 |
| v1.9 | FastAPI 后端基础、React 工作台、SSE 问答与前后端联调测试 |
| v1.9.1 | 真实服务探活、RAG 闭环、浏览器 E2E、文档管理与工作台交互完善 |
| v2.0 | 统一 Compose、前后端 Dockerfile、CI 自动回归、演示脚本与发布收口 |


## 项目结构

```text
DocuMind/
├── app/
│   ├── config.py                 # Pydantic Settings 配置
│   ├── core/
│   │   ├── document_loader.py    # PDF/DOCX/TXT 加载与文档元数据
│   │   ├── document_chunker.py   # 分块与稳定 Chunk ID
│   │   ├── embedding_client.py   # 多 Provider Embedding
│   │   ├── vector_store.py       # Milvus Collection/upsert/search/delete
│   │   ├── retriever.py          # Dense、BM25、RRF、多查询与重排编排
│   │   ├── query_rewriter.py     # 严格 JSON Query Rewrite 与确定性映射
│   │   ├── reranker.py           # 延迟加载 Cross-Encoder 重排
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
│   ├── services/
│   │   ├── rag_service.py        # 检索、生成与结构化流式事件
│   │   └── document_service.py   # 上传、生命周期摄取和文档列表
│   ├── api/
│   │   ├── main.py               # FastAPI 应用工厂和 ASGI 入口
│   │   ├── schemas.py            # API 请求/响应模型
│   │   ├── sse.py                # SSE 事件编码
│   │   └── routers/              # health/system/documents/chat 路由
│   └── utils/
│       ├── logger.py             # 日志兼容入口
│       └── monitoring.py         # 生成器安全的耗时工具
├── tests/                        # unittest 自动化测试和示例文本
├── evaluation/                   # 黄金评估集、离线 Runner、报告和回归门禁
│   ├── datasets/                 # v1.4 与 v1.6 黄金数据集
│   ├── baselines/
│   ├── reports/
│   ├── comparison.py             # 四模式同配置校验与质量/延迟矩阵
│   ├── comparison_runner.py      # v1.7.1 四模式比较 CLI
│   ├── rewrite_artifacts.py
│   ├── rewrite_runner.py
│   └── runner.py
├── frontend/                     # React + TypeScript + Vite 工作台
│   ├── src/App.tsx               # 问答、文档管理、引用和服务状态界面
│   ├── src/api.ts                # REST/SSE 客户端
│   ├── src/conversations.ts      # 本地对话历史与持久化边界
│   ├── src/types.ts              # 前端 API 类型
│   ├── e2e/                      # Playwright 浏览器链路与 Mock API
│   └── package.json              # 前端脚本与依赖
├── infra/milvus/compose.yaml     # Milvus Standalone 基础设施
├── data/                         # 运行数据（Git 忽略）
├── logs/                         # 日志（Git 忽略）
├── .env.example                 # 无密钥配置模板
├── requirements.txt
├── requirements-dev.txt
├── OBSERVABILITY.md              # 日志、指标、追踪指南
├── EVALUATION.md                 # v1.4-v1.7 评估、报告和回归门禁指南
└── web_app.py                    # Gradio 兼容入口
```

## 环境要求

- Windows PowerShell（以下命令以 Windows 为例）
- Python 3.11（v2.0 Docker 与 CI 的正式验证基线）
- 一个可访问的 Milvus Standalone 服务（默认 `http://127.0.0.1:19530`）
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

本项目只将 Milvus Standalone 作为本地基础设施容器化；RAG 应用本身继续在 Windows Python 环境中运行。先启动 Standalone，再在 `.env` 中配置 `MILVUS_URI`；无认证的本地服务可将 `MILVUS_TOKEN` 留空。

Windows 安装并启动 Docker Desktop（使用 WSL2 后端）后，在项目根目录执行：

```powershell
docker compose -f infra/milvus/compose.yaml up -d
docker compose -f infra/milvus/compose.yaml ps
Test-NetConnection 127.0.0.1 -Port 19530
```

`19530` 仅绑定到本机，供 Windows 中运行的 RAG 应用访问。Milvus、etcd 和 MinIO 的数据保存在 Docker 命名卷中，不会写入 Git 工作区。日常停止或恢复服务使用：

```powershell
docker compose -f infra/milvus/compose.yaml stop
docker compose -f infra/milvus/compose.yaml start
```

需要移除容器但保留数据时使用 `docker compose -f infra/milvus/compose.yaml down`；只有确认要删除全部本地向量数据时才使用 `down -v`。

默认 Embedding Provider 是 Ollama：

```powershell
ollama serve
ollama pull qwen3-embedding
```

验证真实 Milvus Standalone 的读写路径：

```powershell
$env:MILVUS_INTEGRATION_TEST="1"
python -m unittest tests.test_milvus_integration -v
Remove-Item Env:MILVUS_INTEGRATION_TEST
```

然后在 `.env` 中为所选 LLM 填写 API Key。例如使用 OpenAI 时填写：

```dotenv
DEFAULT_LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key
```

### 5. 启动 FastAPI 后端与 React 工作台（本地开发链路）

终端一启动 API：

```powershell
python -m app.api
```

默认 API 地址为 `http://127.0.0.1:8001`，Swagger 文档为 `http://127.0.0.1:8001/docs`。另开一个终端启动前端：

```powershell
cd frontend
npm install
npm run dev
```

默认工作台地址为 `http://127.0.0.1:5173`。前端默认请求 `http://127.0.0.1:8001`；跨主机或端口时可在 `frontend/.env.local` 设置 `VITE_API_BASE_URL`。

### 5A. 使用统一 Docker Compose（v2.0 交付链路）

根目录 `compose.yaml` 会同时启动 FastAPI、React、Milvus、etcd 和 MinIO。该方式面向本地演示和交付验收，仍需要宿主机 Ollama 服务和所选 LLM Provider 的 API Key。

```powershell
Copy-Item .env.example .env
# 在 .env 中填写 DEFAULT_LLM_PROVIDER 与对应 API Key
ollama serve
ollama pull qwen3-embedding
docker compose up --build
```

默认访问地址：

- React 工作台：`http://127.0.0.1:5173`
- FastAPI：`http://127.0.0.1:8001`
- Swagger：`http://127.0.0.1:8001/docs`
- Metrics：`http://127.0.0.1:8000/metrics`
- Milvus：`http://127.0.0.1:19530`

Docker 中的 API 默认通过 `http://host.docker.internal:11434` 访问宿主机 Ollama。若运行环境不支持该地址，可在 `.env` 中设置 `DOCKER_OLLAMA_BASE_URL`，不要复用本地 Python 进程使用的 `OLLAMA_BASE_URL=http://localhost:11434`。

如果已经启动了 `infra/milvus/compose.yaml`，它会占用 `19530` 和 `9091`。可以先停止旧基础设施栈，或者为根级栈设置替代宿主端口：

```dotenv
MILVUS_HOST_PORT=19531
MILVUS_HEALTH_HOST_PORT=9092
```

如果本地开发进程已经占用 API 或 Metrics 端口，也可以设置替代宿主端口。前端镜像的 API 地址默认会跟随 `API_HOST_PORT`：

```dotenv
API_HOST_PORT=8002
METRICS_HOST_PORT=8003
```

如果 `docker compose up --build` 在拉取基础镜像或 Python 依赖时超时，说明当前 Docker Hub 或 PyPI 访问不稳定。先确认 Docker Desktop 可以正常联网，或配置可用的镜像加速源后重试；Compose 配置本身可用 `docker compose -f compose.yaml config --quiet` 做离线语法校验。

也可以临时指定可访问的基础镜像源：

```dotenv
PYTHON_BASE_IMAGE=docker.m.daocloud.io/python:3.11-slim
NODE_BASE_IMAGE=hub.rat.dev/node:22-alpine
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
TORCH_TRUSTED_HOST=download.pytorch.org
```

这些变量只影响 Docker 镜像构建。后端镜像默认从 PyTorch 官方 CPU wheel 源预装 `torch`，避免 Cross-Encoder 依赖引入数 GB 的 CUDA 运行库。使用 HTTPS 镜像时通常不需要 `PIP_TRUSTED_HOST` 或 `TORCH_TRUSTED_HOST`；仅在当前网络的证书校验确实失败且你信任对应镜像站时再设置。

停止服务但保留数据：

```powershell
docker compose stop
```

移除容器但保留命名卷：

```powershell
docker compose down
```

主要 API：

- `GET /api/v1/health/live`：进程存活检查；
- `GET /api/v1/health/ready`：Milvus、Embedding、LLM 和注册表就绪检查；
- `GET /api/v1/system/config`：返回前端所需的非敏感配置；
- `GET /api/v1/documents`：文档列表；
- `POST /api/v1/documents`：multipart 文档上传与同步索引；
- `GET /api/v1/documents/{document_key}`：文档详情、活动版本和索引历史；
- `POST /api/v1/documents/{document_key}/reindex`：基于持久化源文件重新建立索引；
- `DELETE /api/v1/documents/{document_key}`：删除注册表记录、Milvus 向量和无引用源文件；
- `POST /api/v1/chat/stream`：返回 `status`、`sources`、`token`、`done/error` SSE 事件。

上传示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8001/api/v1/documents" `
  -F "file=@.\tests\knowledge_base.txt"
```

流式问答示例：

```powershell
curl.exe -N -X POST "http://127.0.0.1:8001/api/v1/chat/stream" `
  -H "Content-Type: application/json" `
  -d '{"question":"文档主要介绍了什么？"}'
```

前端验证命令：

```powershell
cd frontend
npm test
npm run typecheck
npm run build
npm run test:e2e
```

### 5B. 运行完整演示

现场演示、录屏、典型问题、预期答案、Metrics 展示和故障备用方案见 [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md)。演示默认使用 `tests/knowledge_base.txt`，建议在正式展示前按脚本完整走场一次。

### 6. 启动 Gradio 兼容入口

```powershell
python web_app.py
```

默认访问地址：`http://127.0.0.1:7860`。

### 7. 生命周期运维命令

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

命令支持 `--json` 输出，便于脚本和后续任务系统接入。`audit` 同时检查 active 缺失与 Chunk 数不一致；`cleanup` 默认只处理注册表中的旧版本，并可恢复中断在 `deleting` 的清理。确认需要处理整个 Milvus Collection 中未注册的索引时再加 `--include-orphans`。

`rebuild --dry-run` 会校验持久化源文件哈希，并按当前 Chunk/Embedding 配置计算 planned `index_id` 和 `configuration_changed`；Provider/模型未变化时复用上次成功索引验证过的真实维度，源文件缺失或被篡改时直接报错。

`rebuild --retry` 只回收指定文档下唯一的中断 `indexing` 目标，包括尚未切换 active 的新版本。若没有中断目标、同时存在多个目标，或当前配置已无法生成原 `index_id`，命令会拒绝执行并给出错误。

## 关键配置

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `CHUNK_SIZE` | `500` | Chunk 字符长度 |
| `CHUNK_OVERLAP` | `100` | Chunk 重叠长度，必须小于 `CHUNK_SIZE` |
| `RETRIEVAL_TOP_K` | `3` | 返回候选数量 |
| `RETRIEVAL_SCORE_THRESHOLD` | 空 | Milvus L2 最大距离；越小越严格 |
| `MILVUS_URI` | `http://127.0.0.1:19530` | Milvus Standalone 服务地址 |
| `MILVUS_TOKEN` | 空 | 可选认证 Token |
| `MILVUS_DB_NAME` | `default` | Milvus Database 名称 |
| `COLLECTION_NAME` | `rag_documents` | Milvus Collection 名称 |
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

离线运行默认黄金评估集，不需要 Ollama、Milvus、网络或真实 LLM：

```powershell
python -m evaluation.runner `
  --dataset evaluation/datasets/golden_dataset.jsonl `
  --output-json evaluation/reports/demo.json `
  --output-markdown evaluation/reports/demo.md
```

数据格式、指标语义、Adapter 接入方式和回归门禁见 [EVALUATION.md](EVALUATION.md)。

运行 v1.6 三种确定性检索对照：

```powershell
python -m evaluation.runner --dataset evaluation/datasets/v1_6/golden_dataset.jsonl --retrieval-mode dense
python -m evaluation.runner --dataset evaluation/datasets/v1_6/golden_dataset.jsonl --retrieval-mode bm25
python -m evaluation.runner --dataset evaluation/datasets/v1_6/golden_dataset.jsonl --retrieval-mode hybrid
```

运行 v1.6.1 独立 holdout 和真实 Provider 校准：

```powershell
python -m evaluation.runner --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl --retrieval-mode hybrid
python -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2
```

离线命令使用哈希 Embedding 验证检索与评估边界，不代表生产 Embedding 质量。真实 Provider 对照支持 `dense|bm25|hybrid`，详细参数、报告和门禁命令见 [EVALUATION.md](EVALUATION.md)。

### v1.7 Query Rewrite 与 Reranker 实验

先生成同时绑定 schema 版本、Prompt SHA-256、生成参数和数据集 SHA-256 的 Query Rewrite artifact，再运行本地检索评估。生成 artifact 会调用指定 LLM，检索评估阶段不再访问 LLM：

```powershell
python -m evaluation.rewrite_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --provider deepseek --model deepseek-chat `
  --max-rewrites 2 --max-tokens 256 `
  --output evaluation/datasets/v1_7/holdout_rewrites_deepseek.json

python -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2 `
  --enhancement-mode rewrite `
  --rewrite-map evaluation/datasets/v1_7/holdout_rewrites_deepseek.json
```

仅运行真实 Cross-Encoder 重排时，先确保模型已缓存，再加 `--reranker-local-files-only` 以禁止评估阶段探测外网：

```powershell
python -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2 `
  --enhancement-mode rerank `
  --reranker-model BAAI/bge-reranker-base `
  --reranker-local-files-only
```

实验链路只用于评估，不会改变 Web 默认行为；使用 `evaluation.regression_runner` 对相同 holdout 执行门禁后，才考虑后续线上接入。

v1.7.1 使用 `evaluation.comparison_runner` 对 `baseline`、`rewrite`、`rerank` 和 `rewrite-rerank` 四份报告执行严格同配置校验，并统一输出质量指标、平均/P50/P95/最大延迟及相对基线变化；不同 Embedding、分块、阈值或 Hybrid 参数的报告会被拒绝直接比较。

本机最终 holdout 结果如下。四种模式的 Recall@3、文档级 Precision@3、no-answer 准确率和成功率分别均为 `1.0`、`0.3333`、`1.0` 和 `1.0`：

| 模式 | MRR@3 | 平均耗时 | P50 | P95 |
|---|---:|---:|---:|---:|
| baseline | 0.9545 | 308.3 ms | 308.7 ms | 325.7 ms |
| rewrite | 1.0000 | 890.2 ms | 878.5 ms | 961.4 ms |
| rerank | 1.0000 | 1018.9 ms | 690.0 ms | 2462.0 ms |
| rewrite-rerank | 1.0000 | 1742.6 ms | 1674.4 ms | 2608.7 ms |

三种增强模式都修正了唯一一条排序误差，但没有质量差异。Rewrite 的尾延迟明显低于两个 Reranker 模式，因此是后续受控接入验证的首选；组合模式没有额外质量收益，不应启用。12 条 holdout 仍不足以支持直接修改 Web 默认链路。

## 测试与检查

项目测试使用标准库 `unittest`，不依赖 pytest 也可运行：

```powershell
python -m pytest -q
python -m unittest discover -s tests -p "test_*.py" -v
python -m black --check app evaluation tests web_app.py
python -m compileall -q app evaluation web_app.py tests
python -m pip check
```

v2.0 收尾回归结果为：Python 3.11 容器与本机兼容环境均为 `178 passed, 1 skipped, 11 subtests passed`，前端 Vitest `5 passed`，Playwright `6 passed`，Black、`compileall`、TypeScript 类型检查和生产构建通过。完整自动回归不需要真实 Milvus；`tests.test_milvus_integration` 仅在显式设置 `MILVUS_INTEGRATION_TEST=1` 时连接本机服务，完整 Compose 栈另行完成真实 Milvus 启动验证。

## 数据和索引

- 向量索引位于 `MILVUS_URI` 指向的 Milvus 服务中，默认 Collection 为 `rag_documents`
- 文档注册表：`data/document_registry.sqlite3`
- 上传源文件持久化目录：`data/uploads/`（按内容哈希命名，已加入 Git 忽略）
- 日志目录：`logs/`
- 上述运行数据均应保持在 Git 之外。

相同文件名且内容完全相同的文档会得到相同 `document_key`、`document_version_id`、`index_id` 和 `chunk_id`，健康索引的重复上传不会增加 Chunk。如果 active 向量缺失或数量不一致，重复上传会自动进入修复构建。内容更新会先构建新索引，成功后才切换 active；失败时旧 active 仍可检索。

### 清空并重建索引

优先使用生命周期命令清理文档版本。如果需要更换 Embedding 空间，请停止 Web 服务，设置一个新的 `COLLECTION_NAME`，删除生命周期注册表，再重新上传原始文档：

```powershell
Remove-Item -Force .\data\document_registry.sqlite3
```

v1.8 采用“新 Collection 全量重建”完成 Chroma 到 Milvus 的迁移，不读取旧 Chroma 二进制库。确认旧 Milvus Collection 不再使用后，可通过 Milvus 管理工具删除；应用不会因删除 SQLite 注册表而自动删除远端 Collection。

## 已知限制

- React 工作台当前是本地单用户界面；对话历史保存在浏览器 `localStorage`，不会进入后端，也不会参与历史感知检索。
- FastAPI 与 React 已完成真实闭环、浏览器回归和本地 Compose 收尾配置，但还没有认证、异步任务队列、生产部署策略或 API 兼容策略。
- v1.4 之前写入的旧向量没有 `index_id`，当前检索会兼容保留；`audit` 会报告 legacy Chunk，后续可安排显式迁移。
- 迁移前的 Chroma Collection 不受新适配器管理，需要在 Milvus 中使用新 Collection 全量重建。
- 非空 Collection 禁止切换 Embedding Provider、模型或维度；当前版本不提供跨向量空间的在线 shadow migration，更换模型需使用新 Collection 或清空后全量重建。
- 当前是同步生命周期流程；Celery/Redis 异步摄取、认证和多租户授权属于 v2.1 以后。
- 目前是本地单用户应用，没有认证、租户隔离和生产级限流。
- 当前仍只提供应用内 Metrics 和可选 OTLP Trace 导出；Prometheus、Grafana、Jaeger 与 Collector 的部署不属于 v2.0。

## v2.1+ 路线

v2.0 已完成“可演示、可部署、可验收”的交付目标。后续版本按系统边界分阶段推进：

1. 在 v2.1 引入认证与用户边界，并基于认证上下文实现真实租户资源隔离；
2. 在 v2.1-v2.2 评估 Celery/Redis 异步摄取、任务取消、失败重试和并发一致性；
3. 按部署需要补充 Prometheus、Grafana、Jaeger/Collector 外部栈与告警；
4. 扩大 holdout 数据后，继续验证 Query Rewrite 的可选质量模式，Reranker 保持受控实验。

上述功能会引入新的安全、任务状态或运维边界，因此不回填到 v2.0。

## 常见问题

### 系统初始化失败

检查：

1. `.env` 中选定的 Provider 是否有 API Key；
2. `MILVUS_URI` 指向的 Standalone 服务是否正在运行且网络可达；
3. Ollama 是否正在运行，Embedding 模型是否已下载；
4. `pip check` 是否通过；
5. `logs/` 中是否有完整异常。

### 上传后没有结果

- 确认文档有可提取文本；扫描版 PDF 暂不包含 OCR。
- 如果配置了 `RETRIEVAL_SCORE_THRESHOLD`，可适当调大或暂时留空。
- “系统错误”和“无检索结果”已分开处理，系统错误请查看日志。

### 更换 Embedding 模型后查询失败

系统会在写入和查询前校验 Collection 保存的 Embedding Provider、模型和维度，同维度的不同模型也会被拒绝，避免语义空间静默混用。停止服务后改用新的 `COLLECTION_NAME` 并全量重建；确认旧索引无需保留时，再通过 Milvus 管理工具删除旧 Collection。
