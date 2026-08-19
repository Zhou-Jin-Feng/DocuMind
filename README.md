# DocuMind - RAG 知识库问答系统（v2.0.5）

一个本地单用户 RAG 知识库问答系统。当前主链路采用 FastAPI、React/TypeScript、Milvus Standalone 和 SSE 流式响应，包含文档生命周期管理、真实依赖探活、引用来源、结构化可观测性、离线评测和自动质量回归门禁。

> GitHub 已发布 tag 仍为 `v2.0`。本地 `main` 已包含 v2.0.4，当前代码版本为 v2.0.5；v2.0.1 至 v2.0.5 的维护版本 tag 均尚未创建。

## 核心能力

- PDF、DOCX、TXT 上传、稳定分块、内容寻址保存和幂等索引。
- SQLite Registry 管理文档、内容版本、索引版本、active 切换和失败恢复。
- Milvus Standalone 保存向量，etcd 和 MinIO 由 Docker Compose 编排。
- FastAPI 提供健康检查、配置、文档管理和 SSE 问答 API。
- React 工作台提供上传进度、文档详情、引用来源和本地对话历史。
- 默认 Web 检索保持 Dense-only；BM25、Hybrid/RRF、Query Rewrite 和 Reranker 保留为离线评测能力。
- JSONL 日志、Prometheus Metrics、OpenTelemetry Tracing 和 Request/Trace ID 关联。
- 确定性黄金集、JSON/Markdown 报告、输入兼容检查和 PR CI 质量门禁。
- 独立的答案质量数据契约、28 条 holdout 黄金集、真实/Fake Generator/Judge、严格 Judge JSON、逐案例失败隔离和原子 JSON/Markdown 报告。

## 文档导航

| 文档 | 职责 |
|---|---|
| [架构说明](docs/ARCHITECTURE.md) | 分层、调用链、数据不变量和系统边界 |
| [项目结构](docs/PROJECT_STRUCTURE.md) | 目录、模块职责和依赖方向 |
| [评测指南](docs/EVALUATION.md) | 数据集、指标、基线、Runner 和 CI 回归门禁 |
| [可观测性指南](docs/OBSERVABILITY.md) | 日志、Metrics、Tracing 和隐私边界 |
| [依赖说明](docs/DEPENDENCIES.md) | 直接依赖、安装边界和可复现性 |
| [运行示例](docs/DEMO_SCRIPT.md) | 启动、端到端流程和故障处理 |
| [版本历史](docs/VERSION_HISTORY.md) | 主要版本与架构变化 |

## 环境要求

- Python 3.11
- Node.js 22
- Docker Desktop / Docker Engine + Compose
- 本地 Ollama `qwen3-embedding`，或另行配置兼容的 Embedding Provider
- OpenAI、Anthropic Claude、DeepSeek 或 GLM 中至少一个 LLM Provider

## 快速开始

### 统一 Docker Compose

```powershell
Copy-Item .env.example .env
ollama serve
ollama pull qwen3-embedding
# 在 .env 中配置 DEFAULT_LLM_PROVIDER 和对应 API Key
docker compose up --build
```

默认地址：

- React 工作台：`http://127.0.0.1:5173`
- FastAPI：`http://127.0.0.1:8001`
- Swagger：`http://127.0.0.1:8001/docs`
- Metrics：`http://127.0.0.1:8000/metrics`
- Milvus：`http://127.0.0.1:19530`

Compose 内的 API 默认通过 `http://host.docker.internal:11434` 访问宿主机 Ollama。端口冲突或跨主机配置见 `.env.example` 中的 `*_HOST_PORT`、`DOCKER_OLLAMA_BASE_URL` 和 `VITE_API_BASE_URL`。

停止服务但保留数据：

```powershell
docker compose stop
```

移除容器但保留命名卷：

```powershell
docker compose down
```

只有确定要删除全部本地 Milvus 和应用数据时才使用 `docker compose down -v`。

### 本地开发

创建环境并安装依赖：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

只启动 Milvus 基础设施：

```powershell
docker compose -f infra/milvus/compose.yaml up -d
```

启动 API：

```powershell
python -m app.api
```

另开终端启动前端：

```powershell
cd frontend
npm ci
npm run dev
```

Gradio 兼容入口仍可通过 `python web_app.py` 启动，但不再是主要交付界面。

## API 概览

| 方法与路径 | 用途 |
|---|---|
| `GET /api/v1/health/live` | API 进程存活检查 |
| `GET /api/v1/health/ready` | Milvus、Embedding、LLM 和 Registry 就绪检查 |
| `GET /api/v1/system/config` | 返回前端需要的非敏感配置 |
| `GET /api/v1/documents` | 文档列表 |
| `POST /api/v1/documents` | 上传并同步建立索引 |
| `GET /api/v1/documents/{document_key}` | 文档详情和索引历史 |
| `POST /api/v1/documents/{document_key}/reindex` | 基于持久化源文件重建索引 |
| `DELETE /api/v1/documents/{document_key}` | 可恢复地删除注册表、向量和无引用源文件 |
| `POST /api/v1/chat/stream` | 返回 `status/sources/token/done/error` SSE 事件 |

## 生命周期运维

```powershell
python -m app.lifecycle list
python -m app.lifecycle audit
python -m app.lifecycle cleanup --dry-run
python -m app.lifecycle cleanup --include-orphans
python -m app.lifecycle rebuild --document-key <document_key> --dry-run
python -m app.lifecycle rebuild --document-key <document_key>
python -m app.lifecycle rebuild --document-key <document_key> --retry
```

`rebuild --dry-run` 不连接 Embedding Provider，也不写 Registry 或 Milvus。真实重建会校验内容寻址源文件、Embedding 空间和 Chunk 数量，成功后才切换 active 索引。

## 确定性质量门禁

生成与 CI 相同的实时 Dense 报告：

```powershell
.\venv\Scripts\python.exe -m evaluation.runner `
  --dataset evaluation/datasets/golden_dataset.jsonl `
  --retrieval-mode dense `
  --output-json evaluation/reports/current-deterministic.json `
  --output-markdown evaluation/reports/current-deterministic.md

.\venv\Scripts\python.exe -m evaluation.regression_runner `
  --baseline evaluation/baselines/deterministic_dense_v2.json `
  --current evaluation/reports/current-deterministic.json
```

普通 PR CI 只使用仓库内数据、确定性哈希 Embedding 和内存向量存储，不连接 Ollama、Milvus、Hugging Face 或付费 LLM。JSON/Markdown 报告无论门禁成功或失败都会作为 Artifact 保留 14 天。详细指标语义和基线边界见[评测指南](docs/EVALUATION.md)。

## 答案质量 Runner

答案质量 CLI 使用当前生产 `RAGGenerator` Prompt 生成候选答案，并使用独立 Judge Prompt 评估 Faithfulness、引用质量和回答相关性。生成模型与 Judge 必须分别指定并记录：

```powershell
.\venv\Scripts\python.exe -m evaluation.answer_runner `
  --dataset evaluation/datasets/v2_answer_quality/dataset.jsonl `
  --documents-dir evaluation/datasets/v2_answer_quality/documents `
  --retrieval-mode dense `
  --embedding-provider ollama `
  --generator-provider openai `
  --generator-model gpt-4-turbo `
  --judge-provider openai `
  --judge-model gpt-4-turbo `
  --output-json evaluation/reports/answer-quality-current.json `
  --output-markdown evaluation/reports/answer-quality-current.md
```

退出码 `0` 表示所有案例执行成功并写出报告，`1` 表示报告已写出但存在案例错误，`2` 表示数据集、配置、Provider 初始化或输出路径错误。真实答案评测不进入普通 PR CI；运行前必须冻结模型名、参数、数据集和语料，且不得把 API Key 写入命令或报告。

v2.0.5 的专用数据集包含 28 条人工编写的答案质量 `holdout`：8 条直接事实、5 条多片段综合、6 条无答案、3 条信息不足或冲突、3 条 Prompt Injection、3 条引用边界。独立阈值集另含 validation 5 正/15 负和 holdout 5 正/10 负，共 35 条；它只冻结后续校准输入，尚未执行阈值扫描。11 份 TXT 语料均为仓库内合成材料，不含私人文档或真实凭据；规范化指纹为答案集 `f5eb00ddc448772e6369f8e2b8ae798cecf4736e2f7dc6619df49a728108055d`、阈值集 `8853bf2aba5bc1266bd7202b6f7feb084a0fca242d475d6c2204928fdab12210`、语料 `7655501aca56852fd4db7755b8fea6512705b837cd070d5e9e00ad373a878103`。

## 测试与检查

```powershell
python -m pytest -q
python -m black --check app evaluation tests web_app.py
python -m compileall -q app evaluation web_app.py tests
python -m pip check

cd frontend
npm test
npm run typecheck
npm run build
npm run test:e2e

cd ..
docker compose -f compose.yaml config --quiet
docker compose -f infra/milvus/compose.yaml config --quiet
```

v2.0.1 完整本地回归结果为 Python `181 passed, 1 skipped, 11 subtests passed`、Vitest `5 passed`、Playwright `6 passed`，并通过格式、编译、依赖、TypeScript、构建和两份 Compose 校验。v2.0.2 进一步验证了正常确定性报告返回 `PASS`，仅降低兼容报告的 Recall 会返回质量失败码 `1`。v2.0.3 全量 Python 回归为 `189 passed, 1 skipped, 20 subtests passed`。v2.0.4 全量 Python 回归为 `197 passed, 1 skipped, 23 subtests passed`。v2.0.5 全量 Python 回归为 `205 passed, 1 skipped, 124 subtests passed`，数据集专项为 `8 passed, 101 subtests passed`，Vitest `5 passed`，Playwright `6 passed`，并通过 Black、compileall、`pip check`、TypeScript、前端生产构建、两份 Compose 和既有确定性检索门禁。

## 版本摘要

| 版本 | 主要内容 | 状态 |
|---|---|---|
| v2.0 | FastAPI/React/Milvus 统一 Compose、基础 CI、演示与发布收口 | 已发布并推送 tag |

完整历史和真实提交边界见[版本历史](docs/VERSION_HISTORY.md)。

## 当前边界

- 本地单用户系统，没有认证、真实租户隔离、限流或生产高可用承诺。
- 文档摄取是同步操作，没有任务队列、取消或后台重试调度器。
- 默认 LLM Provider 是 OpenAI；Embedding 默认使用本地 Ollama，普通 Web 闭环并非默认完全离线。
- Query Rewrite、Hybrid 和 Reranker 尚未进入 Web 默认请求路径。
- 当前 8 条确定性数据集只用于管线回归，不能代表生产答案质量。
- 检索命中正确文档不等于最终回答忠实；Faithfulness 和引用质量必须由独立答案评测验证。
- v2.0.5 已冻结答案与阈值数据集和 11 份专用语料，但尚未运行和人工复核真实模型报告，也未扫描或启用检索阈值，因此不能声明当前生产答案或拒答能力已通过验收。
- 当前 Generator 刻意复用未加固的生产 Prompt；Prompt Injection 防护、统一 `[文档N]` 约束和温度对照必须在旧 Prompt 基线完成后单独实施。
- Prometheus、Grafana、Jaeger 和 Collector 等外部可观测性后端不在 Compose 中。
