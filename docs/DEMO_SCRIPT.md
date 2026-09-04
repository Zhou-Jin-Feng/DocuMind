# DocuMind - RAG 系统 v2.0 演示脚本

本文档提供本版本的启动、就绪检查、端到端操作、可观测性检查和故障处理步骤。

## 1. 演示边界

- 正式 Python 基线：Python 3.11；
- 默认入口：Docker Compose + React 工作台；
- Embedding：宿主机 Ollama `qwen3-embedding`；
- LLM：`.env` 中选定的 OpenAI、DeepSeek、Anthropic 或 GLM；
- 向量数据库：Compose 内的 Milvus Standalone；
- 演示文档：`tests/knowledge_base.txt`；
- 当前安全边界：本机单用户、仅绑定 `127.0.0.1`、无认证；
- 不在演示中承诺：多用户、异步摄取、生产部署、Kubernetes 或完整监控平台。

## 2. 演示前准备

建议至少提前一天完成首次镜像构建、模型下载和完整走场。现场只展示已经验证过的流程。

### 2.1 环境检查

需要准备：

- Docker Desktop，并确保 Docker Engine 正常运行；
- Ollama，并已下载 `qwen3-embedding`；
- Node.js 22，仅在需要单独运行前端或 E2E 时使用；
- Python 3.11，仅在需要本地开发启动或运行后端测试时使用；
- 一个可用的 LLM Provider API Key；
- 仓库根目录下的 `.env`，不得在演示画面中展示 API Key。

初始化配置：

```powershell
Copy-Item .env.example .env
ollama pull qwen3-embedding
```

连续检索演示默认将 Embedding 模型保留 10 分钟，减少空闲后首次请求的冷启动；该设置仍是
有界的，避免与同一 GPU 上的生成模型形成永久驻留竞争。如需调整，在 `.env` 中设置：

```dotenv
OLLAMA_EMBEDDING_KEEP_ALIVE_SECONDS=600
OLLAMA_EMBEDDING_READINESS_TIMEOUT_SECONDS=60
```

在 `.env` 中填写 Provider，例如：

```dotenv
DEFAULT_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-api-key
```

启动 Ollama：

```powershell
ollama serve
```

### 2.2 端口预检

默认端口如下：

| 服务 | 地址 |
|---|---|
| React 工作台 | `http://127.0.0.1:5173` |
| FastAPI / Swagger | `http://127.0.0.1:8001` / `http://127.0.0.1:8001/docs` |
| Metrics | `http://127.0.0.1:8000/metrics` |
| Milvus | `127.0.0.1:19530` |
| Milvus 健康端点 | `http://127.0.0.1:9091/healthz` |

检查常用端口：

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 5173,8000,8001,9091,19530 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

若已有本地 API 或 `infra/milvus/compose.yaml` 正在运行，不必强行停止。可在 `.env` 中使用隔离端口：

```dotenv
API_HOST_PORT=8002
METRICS_HOST_PORT=8003
MILVUS_HOST_PORT=19531
MILVUS_HEALTH_HOST_PORT=9092
```

前端镜像会在构建时让 API 地址跟随 `API_HOST_PORT`。修改端口后必须带 `--build` 重新构建前端。

### 2.3 数据预检

演示前打开工作台确认 `tests/knowledge_base.txt` 是否已经存在。若已存在，可选择以下一种处理方式：

1. 保留文档，直接演示幂等上传和重新索引；
2. 在文档详情中删除旧文档，再从空知识库开始演示；
3. 保留既有数据，不演示首次上传，只演示检索和引用。

不要为了清空演示数据直接执行 `docker compose down -v`。该命令会删除 Compose 命名卷，仅应在确认其中没有需要保留的数据时使用。

## 3. 启动与就绪检查

### 3.1 配置检查

```powershell
docker compose -f compose.yaml config --quiet
```

该命令只验证 Compose 解析结果，不会启动容器。若失败，先检查 `.env` 的格式和端口变量。

### 3.2 启动完整栈

```powershell
docker compose up -d --build
docker compose ps
```

首次启动时，API 会连接宿主机 Ollama 并探测 Embedding 维度，可能需要 30-60 秒才从 `health: starting` 变为 `healthy`。不要在 API 尚未就绪时开始上传。

默认端口的就绪检查：

```powershell
$ApiPort = 8001
$MetricsPort = 8000

Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/v1/health/live"
Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/v1/health/ready" |
  ConvertTo-Json -Depth 4
(Invoke-WebRequest "http://127.0.0.1:$MetricsPort/metrics").StatusCode
```

使用替代端口时，将 `$ApiPort` 和 `$MetricsPort` 改为 `.env` 中的值。开始演示前应满足：

- `api`、`frontend`、`milvus`、`etcd`、`minio` 均为 `healthy`；
- `/health/ready` 的 `application`、`milvus`、`embedding`、`llm`、`registry` 均为 `ready`；
- Metrics 返回 HTTP 200；
- 工作台显示“服务就绪”。

## 4. 12 分钟演示流程

| 时间 | 操作 | 需要讲清的内容 |
|---|---|---|
| 0:00-1:00 | 打开 React 工作台 | 前后端分离；默认链路是 React + FastAPI + Milvus |
| 1:00-2:00 | 展示服务状态 | readiness 会真实探测 Milvus、Embedding、LLM 和注册表 |
| 2:00-4:00 | 上传示例文档 | 解析、分块、向量化、写入、校验、激活是同步生命周期 |
| 4:00-5:00 | 打开文档详情 | 展示 active 版本、Chunk 数和索引历史 |
| 5:00-9:00 | 提问 3-5 个问题 | 展示 SSE 流式回答、来源数量和原文片段 |
| 9:00-10:00 | 展示重新索引或幂等上传 | 健康重复上传不会制造重复 Chunk |
| 10:00-11:00 | 打开 Metrics | 展示请求、检索、生成、上传和错误指标 |
| 11:00-12:00 | 总结边界与取舍 | v2.0 是交付收尾版，认证和异步任务后移 |

### 4.1 上传文档

1. 打开 `http://127.0.0.1:5173`；
2. 选择 `tests/knowledge_base.txt`；
3. 点击上传并观察“解析、切分与向量化”等阶段反馈；
4. 等待索引完成；
5. 确认左侧知识库出现文件名和 Chunk 数；
6. 打开文档详情，展示活动版本和索引历史。

讲解重点：

- 文档内容哈希参与稳定 ID 计算；
- 新索引完成写入和数量校验后才切换 active；
- 构建失败不会覆盖旧 active 索引；
- 同内容重复上传会复用健康索引，避免重复向量。

### 4.2 演示问题

以下问题均基于 `tests/knowledge_base.txt`，按现场时间选择 3-5 个。

| 问题 | 预期答案要点 | 展示点 |
|---|---|---|
| `RAG 系统包含哪些核心组件？它的优势是什么？` | 文档加载器、文本分块器、向量化模型、向量数据库、检索器、生成器；优势是结合检索和生成，答案有据可查 | 跨段检索、完整回答、引用来源 |
| `监督学习和无监督学习有什么区别？各举两个文档中的算法例子。` | 监督学习使用标记数据，可举线性回归、逻辑回归；无监督学习处理未标记数据，可举 K-means、PCA | 多片段归纳 |
| `CNN、LSTM 和 Transformer 分别适合处理什么？` | CNN 处理图像；LSTM 处理序列并缓解长期依赖；Transformer 基于注意力机制，在自然语言处理领域表现突出 | 局部事实检索 |
| `文档列出了哪些强化学习方法？` | Q-learning、DQN、策略梯度、Actor-Critic | 精确枚举与来源核对 |
| `文档是否介绍了 XGBoost？只根据文档回答。` | 文档未介绍 XGBoost，应明确说明依据不足，不应编造细节 | 无依据问题和回答边界 |

每次回答至少检查三件事：

1. 文本是否逐步流式出现；
2. 引用来源是否显示 `knowledge_base.txt`；
3. 展开的原文片段是否真的支持答案。

若模型回答与预期措辞不同，以引用片段和事实一致性为判断标准，不要求逐字匹配。

### 4.3 文档生命周期演示

根据时间选择一个动作即可：

- 再次上传同一文件，说明稳定 ID 和幂等索引；
- 在详情中点击重新建立索引，说明基于持久化源文件重建；
- 展示索引历史，说明 active 状态机；
- 删除操作仅使用可丢弃测试文档，并确认目标后执行。

### 4.4 Metrics 演示

完成上传和问答后打开 `http://127.0.0.1:8000/metrics`，或执行：

```powershell
(Invoke-WebRequest "http://127.0.0.1:8000/metrics").Content |
  Select-String "rag_queries_total|rag_retrieval_duration_seconds|rag_documents_uploaded_total"
```

使用替代 Metrics 端口时同步修改 URL。讲解时说明：

- 应用已暴露 Prometheus 指标；
- 日志支持结构化 JSONL 和 `request_id`；
- Trace 支持可选 OTLP 导出；
- Grafana、Jaeger、Collector 的完整部署不属于 v2.0 必选范围。

## 5. 故障备用方案

### 5.1 API 长时间停留在 starting

```powershell
docker compose logs --tail 200 api
Invoke-RestMethod http://127.0.0.1:8001/api/v1/health/ready
```

依次检查：

1. 宿主机 `ollama serve` 是否运行；
2. `ollama list` 是否包含 `qwen3-embedding`；
3. `.env` 中 `OLLAMA_EMBEDDING_KEEP_ALIVE_SECONDS` 是否在 `0-3600` 范围内；
4. `.env` 中 `OLLAMA_EMBEDDING_READINESS_TIMEOUT_SECONDS` 是否在 `>0-60` 范围内；
5. `.env` 中的 LLM Provider 与 API Key 是否匹配；
6. Milvus、etcd、MinIO 是否健康；
7. Docker 是否支持 `host.docker.internal`。

如果 readiness 曾经成功、空闲后又显示 `embedding=unavailable`，先调用一次受控预热并等待
就绪，而不是重新下载模型：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:11434/api/embed" `
  -ContentType "application/json" `
  -Body '{"model":"qwen3-embedding","input":"readiness","keep_alive":600}'
Invoke-RestMethod "http://127.0.0.1:8001/api/v1/health/ready"
```

若 Ollama 地址不可用，在 `.env` 设置：

```dotenv
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### 5.2 端口被占用

在 `.env` 设置替代端口后重新构建：

```powershell
docker compose up -d --build
```

不要只执行 `--no-build`，否则前端镜像中可能仍保留旧 API 地址。

### 5.3 镜像或依赖下载失败

先执行 Compose 配置检查，确认不是语法问题。网络不稳定时使用 README 中记录的 `PYTHON_BASE_IMAGE`、`NODE_BASE_IMAGE`、`PIP_INDEX_URL` 和 `TORCH_INDEX_URL` 镜像参数。

### 5.4 LLM 临时不可用

- 不伪造现场结果；
- 展示 `/health/ready` 的真实失败状态和错误边界；
- 展示已准备的工作台、引用来源和 Metrics 截图；
- 运行 `npm run test:e2e`，说明浏览器主流程使用 Mock API 可独立回归；
- 将故障解释为外部 Provider 依赖，而不是跳过错误。

## 8. 当前验证基线

2026-08-17 已完成以下回归：

| 检查 | 结果 |
|---|---|
| Python 3.11 容器 pytest | `178 passed, 1 skipped, 11 subtests passed` |
| 本机 Python 3.14 兼容检查 | `178 passed, 1 skipped, 11 subtests passed` |
| Black | 82 个文件无需修改 |
| compileall | 通过 |
| Vitest | 2 个文件、5 条测试通过 |
| TypeScript typecheck | 通过 |
| Vite production build | 通过 |
| Playwright Chromium | 6 条工作流通过 |
| 完整 Compose 启动 | 五个服务健康，前端、API、Metrics、Milvus 端点通过 |

其中跳过项是需要显式设置 `MILVUS_INTEGRATION_TEST=1` 的真实 Milvus 集成测试；完整 Compose 栈已另行完成真实 Milvus 启动与就绪验证。

## 9. 演示结束

停止服务并保留数据：

```powershell
docker compose stop
```

移除容器和网络但保留命名卷：

```powershell
docker compose down
```

演示结束后确认没有遗留测试 Web Server，并保留本次使用的 `.env` 在本机，不要提交到 Git。
