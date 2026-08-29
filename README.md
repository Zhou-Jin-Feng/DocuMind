# DocuMind - RAG 知识库问答系统（v2.2.0）

一个本地单用户 RAG 知识库问答系统。当前主链路采用 FastAPI、React/TypeScript、Milvus Standalone 和 SSE 流式响应，包含文档生命周期管理、单文档纯检索、真实依赖探活、引用来源、结构化可观测性、离线评测和自动质量回归门禁。

> GitHub 已发布 tag 仍为 `v2.0`。当前代码版本为 v2.2.0；v2.0.1 至 v2.2.0 的后续版本 tag 均尚未创建。

## 核心能力

- PDF、DOCX、TXT 上传、稳定分块、内容寻址保存和幂等索引。
- SQLite Registry 管理文档、内容版本、索引版本、active 切换和失败恢复。
- Milvus Standalone 保存向量，etcd 和 MinIO 由 Docker Compose 编排。
- FastAPI 提供健康检查、配置、文档管理、单文档纯检索和 SSE 问答 API。
- React 工作台提供上传进度、文档详情、引用来源和本地对话历史。
- 默认 Web 检索保持 Dense-only；BM25、Hybrid/RRF、Query Rewrite 和 Reranker 保留为离线评测能力。
- JSONL 日志、Prometheus Metrics、OpenTelemetry Tracing 和 Request/Trace ID 关联。
- 纯检索独立 readiness、依赖超时、有限重试、进程内并发上限和 W3C Trace Context。
- 确定性黄金集、JSON/Markdown 报告、输入兼容检查和 PR CI 质量门禁。
- 独立的答案质量数据契约、28 条 holdout 黄金集、真实/Fake Generator/Judge、严格 Judge JSON、逐案例失败隔离和原子 JSON/Markdown 报告。
- 人工逐案复核的旧 Prompt 真实对照，明确记录当前拒答和统一引用格式的失败边界。
- 基于独立 validation/holdout 协议的 Dense L2 阈值校准；当前证据明确支持“不启用全局默认阈值”。
- 加固后的不可信上下文 Prompt、XML 边界、统一 `[文档N]` 引用解析，以及低基数线上引用观测。

## 文档导航

| 文档 | 职责 |
|---|---|
| [架构说明](docs/ARCHITECTURE.md) | 分层、调用链、数据不变量和系统边界 |
| [项目结构](docs/PROJECT_STRUCTURE.md) | 目录、模块职责和依赖方向 |
| [评测指南](docs/EVALUATION.md) | 数据集、指标、基线、Runner 和 CI 回归门禁 |
| [可观测性指南](docs/OBSERVABILITY.md) | 日志、Metrics、Tracing 和隐私边界 |
| [纯检索 API](docs/RETRIEVE_API.md) | 单文档 Dense 请求、证据响应、错误码和兼容规则 |
| [ScholarTrace 接入](docs/SCHOLARTRACE_INTEGRATION.md) | Consumer 调用、错误处理、冒烟、升级回滚和服务边界 |
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
| `GET /api/v1/health/ready` | Milvus、Embedding、LLM、Registry 和纯检索能力就绪检查 |
| `GET /api/v1/system/config` | 返回前端需要的非敏感配置 |
| `GET /api/v1/documents` | 文档列表 |
| `POST /api/v1/documents` | 上传并同步建立索引 |
| `GET /api/v1/documents/{document_key}` | 文档详情和索引历史 |
| `POST /api/v1/documents/{document_key}/reindex` | 基于持久化源文件重建索引 |
| `DELETE /api/v1/documents/{document_key}` | 可恢复地删除注册表、向量和无引用源文件 |
| `POST /api/v1/retrieve` | 对指定文档 active index 返回原始 Chunk，不调用 LLM |
| `POST /api/v1/chat/stream` | 返回 `status/sources/token/done/error` SSE 事件 |

`/retrieve` 使用独立 Schema `1.0`，要求调用方提供 `document_key` 和当前
`expected_index_id`。接口仅承诺 Dense L2 检索，正文不截断，单次 `top_k`
范围为 1-20，请求体上限为 16 KiB。完整契约和错误语义见[纯检索 API](docs/RETRIEVE_API.md)，跨仓调用和运维流程见[ScholarTrace 接入](docs/SCHOLARTRACE_INTEGRATION.md)。

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

单文档 `/retrieve` 另有 Chunk 级契约基线：

```powershell
.\venv\Scripts\python.exe -m evaluation.retrieve_quality_runner `
  --json-output evaluation/reports/retrieve_quality_current.json `
  --markdown-output evaluation/reports/retrieve_quality_current.md

.\venv\Scripts\python.exe -m evaluation.regression_runner `
  --baseline evaluation/baselines/retrieve_quality_v1.json `
  --current evaluation/reports/retrieve_quality_current.json `
  --allowed-drop ndcg_at_k=0 `
  --minimum api_bottom_parity_rate=1 `
  --minimum contamination_free_rate=1 `
  --minimum no_answer_empty_accuracy=1
```

该基线通过生产 `RetrievalService` 运行 5 个仓库内确定性案例，只验证 Chunk
排序、空结果、公共/底层一致和跨文档污染，不代表真实 Embedding/Milvus 质量。

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

v2.0.6 使用 Ollama `qwen3-embedding`（4096 维）、DeepSeek `deepseek-chat` Generator/Judge、Dense 检索、空距离阈值和未加固生产 Prompt 生成并人工复核了 [pre-hardening JSON 报告](evaluation/reports/v2_answer_pre_hardening.json)及[可读报告](evaluation/reports/v2_answer_pre_hardening.md)。28 条均成功执行，19 条可回答案例的标注文档全部进入 Top-K；Faithfulness 和回答相关性均为 `1.0000`，但拒答准确率仅为 `0.6786`，引用正确性与完整性均为 `0.0526`。三条 Prompt Injection 未输出哨兵或服从恶意指令。这是旧行为对照，不代表当前答案质量已经通过验收；完整人工结论见[复核记录](evaluation/reports/v2_answer_pre_hardening_review.md)。

v2.0.7 使用相同的 Ollama Embedding、Dense、Milvus L2、Top-K=3 和 11 份专用语料，只在 validation 的 5 条正样本与 15 条困难负样本上运行无阈值检索并扫描 59 个相邻 distance 中点。没有候选同时满足 Recall@3 下降不超过 `0.02`、无答案检索准确率不低于 `0.90` 和执行成功率 `1.00`：约 `0.7175` 的候选可达到 `0.9333` 无答案准确率，但 Recall@3 仅 `0.4000`；保持 Recall@3=`1.0000` 的约 `0.9006` 候选，无答案准确率仅 `0.4667`。因此按预设协议不运行 holdout、不启用参考阈值，代码与 `.env.example` 继续保持空值。机器可读结论见[扫描报告](evaluation/reports/v2_threshold_validation_scan.json)，完整依据见[复核记录](evaluation/reports/v2_threshold_validation_review.md)。

v2.0.8 在同一固定配置下将生产 Prompt 加固为不可信数据边界，并新增生产引用解析/观测。最新干净提交上的加固报告使用 DeepSeek `deepseek-chat` Generator/Judge、Ollama `qwen3-embedding` 4096 维、Dense、Milvus L2、空阈值和 28 条 holdout：`temperature=0.7` 时成功率 `1.0000`、拒答准确率 `0.7500`、Faithfulness/引用正确性/完整性/相关性均为 `0.9474`；预先选定的 `temperature=0.1` 对照成功率为 `0.9643`、拒答准确率为 `0.7037`，其已评估质量指标为 `1.0000`，但有 1 条案例在 Judge 阶段发生 `ValueError`，因此保留生产温度 `0.7`。三条 Injection 在两种温度下均未输出哨兵、system prompt、真实凭据或越界引用。报告与人工复核见 [hardened JSON](evaluation/reports/v2_answer_prompt_hardened.json)、[hardened Markdown](evaluation/reports/v2_answer_prompt_hardened.md)、[低温对照](evaluation/reports/v2_answer_prompt_hardened_low_temp.json) 和 [复核记录](evaluation/reports/v2_answer_prompt_hardened_review.md)。真实 Provider 指标只适用于本次固定数据集、语料和运行配置，不能外推为普遍质量承诺。

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

v2.0.1 完整本地回归结果为 Python `181 passed, 1 skipped, 11 subtests passed`、Vitest `5 passed`、Playwright `6 passed`，并通过格式、编译、依赖、TypeScript、构建和两份 Compose 校验。v2.0.2 进一步验证了正常确定性报告返回 `PASS`，仅降低兼容报告的 Recall 会返回质量失败码 `1`。v2.0.3 全量 Python 回归为 `189 passed, 1 skipped, 20 subtests passed`。v2.0.4 全量 Python 回归为 `197 passed, 1 skipped, 23 subtests passed`。v2.0.5 全量 Python 回归为 `205 passed, 1 skipped, 124 subtests passed`，数据集专项为 `8 passed, 101 subtests passed`。v2.0.6 全量 Python 仍为 `205 passed, 1 skipped, 124 subtests passed`，答案专项为 `23 passed, 113 subtests passed`，Vitest `5 passed`，Playwright `6 passed`；Black、compileall、`pip check`、TypeScript、前端生产构建、两份 Compose、32 份 Markdown 检查和既有确定性检索门禁均通过。

v2.0.7 全量 Python 为 `215 passed, 1 skipped, 124 subtests passed`，阈值专项为 `10 passed`，Vitest 为 `5 passed`，Playwright 为 `6 passed`；Black、compileall、`pip check`、TypeScript、前端生产构建、两份 Compose、35 份 Markdown UTF-8/本地链接检查、正式工件密钥扫描和既有确定性检索门禁均通过。

v2.0.8 当前代码复审为 Python `220 passed, 1 skipped`，专项测试 `35 passed`，Vitest `5 passed`，Playwright `6 passed`；Black、compileall、`pip check`、TypeScript、前端生产构建、两份 Compose 配置解析、44 份 Markdown UTF-8/本地链接检查、5 份正式评测工件密钥模式扫描和 `deterministic_dense_v2` 回归门禁均通过。两份真实报告均在 `对应阶段源码快照` 干净提交上生成并记录 `dirty=false`；当前源码 API/前端镜像已重建，真实 Compose 冒烟通过 `2.0.8` 健康检查、TXT 上传、可回答/无答案 SSE、详情和删除闭环。

v2.1.0 P0 本地复审为 Python `241 passed, 1 skipped, 149 subtests passed`、Vitest `5 passed`、Playwright `6 passed`；Black 检查 99 个 Python 文件，compileall、`pip check`、TypeScript、前端生产构建、两份 Compose 配置解析、40 份已跟踪 Markdown、全部已跟踪 JSON、版本对齐和 `deterministic_dense_v2` 回归门禁均通过。跳过项仍是需要显式启用的真实 Milvus 集成测试；本次没有生成新的真实 Provider 质量结论。

v2.2.0 P1 本地复审为 Python `266 passed, 1 skipped, 168 subtests passed`、Vitest `5 passed`、Playwright `6 passed`；Black 检查 102 个 Python 文件，compileall、`pip check`、TypeScript、前端生产构建、两份 Compose 配置解析、34 份 JSON、42 份 Markdown、本地链接、版本对齐、`deterministic_dense_v2` 和 `retrieve_quality_v1` 回归门禁均通过。当前源码还通过真实 Ollama/Milvus 的 `2.2.0` 独立 API 冒烟：retrieval readiness、TXT 上传、active 状态、W3C Trace Context、3 个 Chunk 纯检索、证据哈希/排序及文档删除闭环均正常。跳过项仍是需显式环境开关的独立 Milvus 集成测试；本次真实冒烟验证装配与协议，不产生通用语义质量或阈值结论。

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
- v2.0.6 已固化真实旧 Prompt 对照；它通过了执行成功率、Faithfulness 和 Injection 人工检查，但拒答与统一引用指标未达目标，因此不能声明当前生产答案质量已通过验收。
- v2.0.7 已完成阈值校准，但结果是不启用全局默认值；项目只能声明“支持显式阈值并有不启用证据”，不能声明参考部署已通过检索阈值实现可靠拒答。
- 当前 Generator 已使用不可信上下文边界和统一 `[文档N]` 约束；真实评测结果仍只适用于固定数据集、语料和 Provider，不能外推为所有模型或用户文档的质量承诺。
- `/retrieve` 首版只服务受信任的本地上游，要求单文档和预期 active index；不支持批量检索、Hybrid/Reranker、缓存、多租户认证或 MCP。
- Prometheus、Grafana、Jaeger 和 Collector 等外部可观测性后端不在 Compose 中。
