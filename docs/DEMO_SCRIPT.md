# 运行与故障处理

适用于当前 FastAPI/React/Milvus 主线。所有命令默认在仓库根执行，PowerShell 示例中的持续服务应使用独立终端。旧架构请使用相应标签自带的说明。

## Compose 运行

1. 确认 Docker 引擎可用；`docker info` 应能返回 Server 信息。
2. 确认 Ollama 已运行；需要手动启动时另开终端运行 `ollama serve`。
3. 不覆盖已有配置，准备模型与 Provider：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
ollama pull qwen3-embedding
```

编辑 `.env` 的 `DEFAULT_LLM_PROVIDER` 和对应凭据，然后启动：

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8001/api/v1/health/live
Invoke-RestMethod http://127.0.0.1:8001/api/v1/health/ready
```

默认前端为 `http://127.0.0.1:5173`，API 为 `http://127.0.0.1:8001`，Metrics 为 `http://127.0.0.1:8000/metrics`。容器经 `host.docker.internal:11434` 访问宿主机 Ollama；跨主机时显式配置 `DOCKER_OLLAMA_BASE_URL`。

首次 Embedding 加载可能导致暂时的 readiness 失败。默认驻留参数为 `OLLAMA_EMBEDDING_KEEP_ALIVE_SECONDS=600`，独立冷加载探活窗口为 `OLLAMA_EMBEDDING_READINESS_TIMEOUT_SECONDS=60`，二者都是有界设置，不是显存容量保证。

## 本地开发

选择 Python 3.11 后建立虚拟环境并安装开发依赖：

```powershell
python --version
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -f infra/milvus/compose.yaml up -d
```

在已激活虚拟环境的终端运行后端：

```powershell
python -m app.api
```

另开终端运行前端：

```powershell
Set-Location frontend
npm ci
npm run dev
```

本地开发与完整Compose不要同时占用相同端口。路径配置详见根目录 [README](../README.md)；从其他cwd启动时，Python包仍必须可发现。

## 最小功能检查

使用可丢弃的安全样例，例如 `tests/knowledge_base.txt`：

1. 工作台依赖状态正常，或按任务确认 `components.retrieval=ready`。
2. 上传样例，等待索引 active，检查文档详情与索引状态。
3. 进行问答，检查流式输出和引用；模拟中止只应停止该次前端请求。
4. 调用纯检索时使用一个 `document_key` 和与详情一致的 `expected_index_id`。
5. 如需删除测试数据，先确认具体文档身份及其是否为本次新建；不要在共享知识库中盲删。

纯检索契约见 [RETRIEVE_API](RETRIEVE_API.md)，Consumer流程见 [SCHOLARTRACE_INTEGRATION](SCHOLARTRACE_INTEGRATION.md)。Mock API 的E2E通过不代表真实模型或数据库集成通过。

## 生命周期维护

先使用只读或预演命令检查目标：

```powershell
python -m app.lifecycle list
python -m app.lifecycle audit
python -m app.lifecycle cleanup --dry-run
python -m app.lifecycle rebuild --document-key <document_key> --dry-run
```

`<document_key>` 必须替换成确认后的目标ID。真正的 cleanup/rebuild 会改变运行数据并可能调用依赖服务，不属于普通启动步骤。不要在没有备份和目标核对时开启孤儿清理或批量重建。维护CLI的目标和作用域以其 `--help` 为准。

## 验证命令

在开发环境中执行：

```powershell
python -m pytest -q
python -m black --check app evaluation tests
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP documind_pycache
python -m compileall -q app evaluation tests
python -m evaluation.runner --output-json artifacts/evaluation/current.json --output-markdown artifacts/evaluation/current.md
python -m evaluation.regression_runner --baseline evaluation/baselines/deterministic_dense_v2.json --current artifacts/evaluation/current.json
docker compose config --quiet
docker compose -f infra/milvus/compose.yaml config --quiet
```

前端检查从 `frontend/` 执行：

```powershell
npm ci
npm test
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

E2E 使用本地 Mock API 和独立端口4173/4174，不应复用现有服务。回环地址被代理时，检查测试进程的 `NO_PROXY`；不应为测试修改系统代理或中断用户服务。真实Milvus测试、真实Provider评测有各自前置条件，不将跳过项算作已完成的集成验证。

## 常见故障

| 现象 | 检查与处理 |
|---|---|
| Docker Desktop已打开但命令不返回 | 先确认后台引擎就绪，再执行项目启动；不要反复提交构建任务 |
| 端口占用 | 使用 `Get-NetTCPConnection` 检查监听者；调整 `.env.example` 列出的 `*_HOST_PORT` 和前后端地址，不直接结束未知进程 |
| readiness为503 | 检查组件状态；Milvus、Embedding和LLM问题分别处理。LLM失败不一定使纯检索不可用 |
| Ollama冷启动或显存不足 | 预热并复查Embedding readiness；按资源调整有界驻留，勿把延迟直接当作模型未安装 |
| 生成过程中断 | 前端保留已收到的token并显示公开错误；结合request_id查日志，不把内部错误文本发给用户 |
| 新索引失败 | 检查失败状态与现有active索引；不要直接清空Registry或向量库 |
| 相对路径与预期不同 | 应用相对路径以项目根解析；明确传给CLI的路径仍按调用者cwd解释 |
| 镜像/依赖下载失败 | 检查网络、代理、镜像或包源，不将安装失败当作业务测试通过 |

日志、指标和Trace字段见 [OBSERVABILITY](OBSERVABILITY.md)。公开问题报告中不得包含真实凭据、私人正文或完整用户路径。

## 停止与数据保留

```powershell
docker compose stop
```

移除容器和网络但保留命名卷：

```powershell
docker compose down
```

`down -v` 会移除相关命名卷，只能在确认数据可丢弃后使用。这里不提供自动重建或迁移用户旧数据的操作；任何升级/恢复都应先核对对应版本说明和备份范围。
