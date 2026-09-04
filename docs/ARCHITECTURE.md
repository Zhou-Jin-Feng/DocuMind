# DocuMind - RAG 系统架构（v2.2.0）

## 1. 分层结构

```mermaid
flowchart TD
    GRADIO["web_app.py / Gradio 兼容入口"] --> CFG["app.config / Settings"]
    FRONTEND["frontend / React + Vite"] --> API["FastAPI /api/v1"]
    API --> CFG
    API --> SERVICE["app.services"]
    CLI["app.lifecycle CLI"] --> REG["DocumentRegistry / SQLite"]
    CLI --> VS
    GRADIO --> LC["DocumentLifecycleService"]
    SERVICE --> LC
    LC --> REG
    LC --> LOAD["Document Loader"]
    LC --> CHUNK["Document Chunker"]
    LC --> EMB["Embedding Client"]
    LC --> VS["VectorStore / pymilvus"]
    VS --> MILVUS["Milvus Standalone"]
    MILVUS --> ETCD["etcd / 元数据"]
    MILVUS --> MINIO["MinIO / 对象存储"]
    GRADIO --> RET["Retriever"]
    SERVICE --> RET
    RET --> EMB
    RET --> VS
    EVAL["evaluation runner"] --> RET
    EVAL --> LEX["BM25Retriever / jieba"]
    EVAL --> HYB["HybridRetriever / RRF"]
    HYB --> RET
    HYB --> LEX
    GRADIO --> GEN["RAGGenerator"]
    SERVICE --> GEN
    GEN --> LLM["UniversalLLMClient"]
    API --> OBS["app.observability"]
    GRADIO --> OBS
    RET --> OBS
    OBS --> LOG["JSONL Logs"]
    OBS --> MET["Prometheus Metrics"]
    OBS --> TRACE["OpenTelemetry Traces"]
```

`app/core` 保持业务能力，`app/observability` 提供横切能力。业务层只调用稳定封装，不直接依赖 Prometheus 注册表、OpenTelemetry 全局 Provider 或日志文件实现。

v2.1 的 HTTP 边界位于 `app/api`：路由只负责协议、校验、SSE 编码和错误映射；`app/services` 负责把 API 请求编排到既有生命周期、检索和生成能力。React 只依赖 `/api/v1` 合约，Gradio 仍可直接调用同一套核心服务。`RetrievalService` 独立于 Generator，供受信任的上游按单文档和 active index 获取原始证据。

## 2. 文档索引流程

```text
上传校验
→ 内容哈希源文件持久化
→ Registry claim（no-op / indexing）
→ 文档加载与分块
→ 生成 index_id / 稳定 chunk_id
→ 批量 Embedding 和维度校验
→ Embedding 空间兼容校验
→ Milvus upsert / Chunk ID 收敛
→ Chunk 数校验
→ Registry active 切换
→ 清理旧索引
```

关键约束：

- 仅允许 `.pdf`、`.docx`、`.txt`；
- 上传扩展名和大小由配置统一控制；
- PDF 页码写入 `page_number`，从 1 开始；
- 相同内容且 active Chunk 完整时在 claim 阶段 no-op；计数异常时自动重建修复；
- 新版本成功写入并校验后才切换 `active_index_id`，失败不会影响旧 active；
- 相同 Chunk ID 使用 `upsert`，并删除同一索引内非预期 ID，重复执行后集合精确收敛；
- 文档数、向量数和向量维度在写入前校验；
- 非空 Collection 的 Embedding Provider、模型和实际维度必须与当前配置一致；
- Gradio 临时绝对路径不写入向量元数据。

文档摄取 Trace：

```text
rag.document.ingest
├── document.load
├── document.chunk
├── embedding.batch
└── vector.upsert
```

## 3. 文档生命周期

`DocumentRegistry` 是文档和索引状态源，SQLite 表分别记录逻辑文档、内容版本、索引清单和操作进度。`document_key` 标识逻辑文档，`document_version_id` 标识源内容版本，`index_id` 标识该版本在某套解析、分块和 Embedding 清单下的索引。

索引切换遵循：

```text
source persist → claim → build → validate → activate → cleanup
```

`audit` 一次扫描 Milvus，报告旧索引、孤儿索引、缺失 active、active Chunk 数不一致和 v1.4 legacy Chunk。旧索引清理先落 `deleting`，再删除向量并落 `deleted`；进程在任一步中断后都可由下一次 `cleanup` 收敛。

API 删除采用可重试的顺序：

```text
校验文档当前状态
→ Registry 撤销 active 并把索引标记为 deleting
→ 按 index_id 删除 Milvus 向量
→ 删除注册表中的索引、版本和文档记录
→ 仅删除不再被其他版本引用的内容寻址源文件
```

若进程在向量清理前后中断，再次删除同一文档会继续收敛，不会把半删除索引重新暴露为 active。重新索引则复用已校验的持久化源文件，走完整 `claim → build → validate → activate → cleanup` 流程。

`rebuild --dry-run` 不初始化 Embedding Provider，也不写入向量或状态。它先校验内容寻址源文件的 SHA-256，再用当前解析、分块和静态 Embedding 配置计算 planned fingerprint / `index_id`；Provider/模型未变化时复用注册表中已验证的真实维度，避免 Ollama 静态默认维度造成误判。

`rebuild --retry` 会在指定文档下寻找唯一的 `indexing` 目标。它既能恢复 active 索引的中断重建，也能恢复尚未切换 active 的新版本；没有目标或存在多个目标时拒绝猜测，配置已变化时要求恢复原配置或执行新的普通重建。

## 4. API 与前端流程

```text
React 工作台
→ GET /api/v1/health/ready + GET /api/v1/system/config
→ GET /api/v1/documents
→ POST /api/v1/documents（multipart 上传）
→ GET /api/v1/documents/{document_key}
→ POST /api/v1/documents/{document_key}/reindex
→ DELETE /api/v1/documents/{document_key}
→ POST /api/v1/retrieve（单文档原始 Chunk JSON）
→ POST /api/v1/chat/stream
→ status → sources → token* → done/error
```

每个响应带 `X-Request-ID`；SSE 事件的数据是公开 API schema，不包含 Prompt、凭据或内部堆栈。API 默认仅允许 `.env` 中列出的本地 CORS 来源。

`/health/live` 只确认 API 进程存活；`/health/ready` 执行有超时上限的 Milvus RPC 和 Ollama Embedding 探测，检查 SQLite 注册表已初始化，并验证 LLM 客户端配置。Embedding 探针与真实 Embedding 请求使用同一个 `OLLAMA_EMBEDDING_KEEP_ALIVE_SECONDS`（默认 600 秒），冷加载使用独立的 `OLLAMA_EMBEDDING_READINESS_TIMEOUT_SECONDS`（默认/最大 60 秒）。这两项只提供有界驻留和有界等待，不能消除模型切换或显存不足。LLM readiness 不发送真实生成请求，避免健康检查消耗外部 API 配额。依赖未就绪时返回 HTTP 503 和分组件状态，React 以轮询方式自动恢复。

纯检索流程：

```text
POST /api/v1/retrieve
→ 校验 Schema 1.0、16 KiB 请求体和 Dense 参数
→ Registry 解析当前作用域的 document 与 active index
→ 核对 expected_index_id
→ tenant/collection/document/index 四字段下推 Milvus
→ 严格后置谓词与 active index 二次核对
→ 白名单映射完整 Chunk、来源、页码、L2 distance 与 SHA-256
→ 同步 JSON 响应，不调用 LLM、Generator 或引用生成器
```

当前接口一次只允许一个文档。无命中返回 `200` 空列表；stale index、生命周期
过渡和依赖故障使用不同机器码。任意 Milvus metadata、绝对路径和内部异常均不
进入公共响应。

文件上传通过 XHR 暴露真实传输百分比；请求体传输完成后，前端进入“解析、切分与向量化”的不确定时长阶段。对话历史只保存在浏览器 `localStorage`，最多保留有限数量的本地会话，不进入后端 RAG 上下文。移动端引用来源使用底部抽屉，关闭后不改变当前回答和来源数据。

## 5. 问答流程

Web 默认问答链路保持 Dense-only：

```text
用户问题
→ Query Embedding
→ Milvus L2 距离检索
→ 最大距离阈值过滤
→ 构建带来源和页码的上下文
→ LLM 流式生成
→ 完成后确定性解析引用（不改写已发送 Token）
→ UI 展示回答和引用来源
```

`RAGGenerator` 把问题和检索资料都放在 `user` 消息中，使用 `<user_question>`、`<retrieved_context>` 和按列表位置生成的 `<document id="N">` 边界。正文、来源和页码属性统一进行 XML 转义；资料被声明为不可信数据，不能升级为系统指令。回答只接受精确 `[文档N]` 引用。`app.core.citations` 同时服务生产观测和离线评测，解析结果只进入 Metrics/日志和报告，不修改流式回答文本或 SSE 事件。

问答 Trace：

```text
rag.query
├── rag.retrieve
│   ├── embedding.query
│   └── vector.search
├── rag.context.build
└── llm.generate
```

距离语义：

- `distance` 越小越相关；
- `score_threshold` 是允许的最大距离；
- `rerank_score` 越大越相关，不能覆盖原始 `distance`。

v1.6 离线评估同时支持 BM25-only 和 Hybrid。BM25 使用 `jieba` 处理中文，并保留英文单词、配置项和错误码；Hybrid 分别扩大 Dense 与词法候选集，再按 Chunk ID 去重并执行 RRF：

```text
Dense ranks ─┐
             ├→ score(d) = Σ 1 / (60 + rank_i(d)) → Top-K
BM25 ranks ──┘
```

RRF 只使用名次，不直接比较 Milvus L2 `distance` 与 BM25 原始分数。v1.6.1 使用 `dense_weight/(rrf_k+dense_rank) + lexical_weight/(rrf_k+lexical_rank)`，候选深度由 `candidate_multiplier` 控制；零权重通道不执行检索。BM25 可用 `lexical_score_threshold` 拒绝低分词法候选。结果分别保留 `distance`、`lexical_score`、`dense_rank`、`lexical_rank` 和 `fusion_score`，方便审计来源。词法候选没有向量距离时，UI 不显示伪造的距离值。

v1.7 仅在评估编排中增加可选链路：

```text
原始问题 + Rewrite artifact
→ 每条查询独立检索
→ stable chunk_id 去重 + Query RRF
→ 扩大候选集
→ Cross-Encoder Reranker
→ Top-K 评估报告
```

原问题必须在改写列表首位；Query RRF 与 Hybrid RRF 分别保存，不能复用或覆盖 `fusion_score`。Cross-Encoder 只改变最终名次并写入 `rerank_score`，不会把其数值伪装成 Milvus distance。LLM 改写先生成与 schema 版本、Prompt SHA-256、生成参数和数据集 SHA-256 绑定的 artifact，之后的本地检索评估不访问 LLM；这使同一 artifact、语料和配置下的报告可复现。四模式比较还会校验 Embedding、分块、阈值和 Hybrid 参数完全一致，并分别报告质量与平均/P50/P95/最大延迟。

## 6. 可观测性架构

### 6.1 请求上下文

`contextvars` 保存 `request_id` 和 `trace_id`，支持同步生成器完整生命周期、嵌套恢复和异常清理。Tracing 开启后，当前 Span 的真实 Trace ID 会临时覆盖备用 Trace ID，使日志与 Trace 可关联。

### 6.2 日志

- 应用入口显式调用 `setup_logger()`；模块导入不创建文件。
- 控制台默认文本，文件默认 JSONL。
- 统一事件名、操作名、状态、数字耗时和异常类型。
- 日志 Patcher 负责字段补全和凭据脱敏。

### 6.3 Metrics

- `configure_metrics()` 只配置内存注册表。
- `start_metrics_server()` 只由 Web 主入口显式调用。
- 标签限制为 `provider`、`operation`、`status`、`error_type`。
- 问答完成后记录引用数量、非法引用数量和无引用状态；不记录回答正文、检索正文或引用集合。
- 关闭后所有操作 no-op，不监听端口。

### 6.4 Tracing

- 使用应用私有 `TracerProvider`，不覆盖 OpenTelemetry 全局 Provider。
- 默认关闭；没有 OTLP endpoint 时不创建网络 Exporter。
- Span 异常只记录 `error.type` 和 ERROR 状态，不发送默认异常事件。
- Span 属性过滤问题、Prompt、文档正文、文件名、凭据及高基数请求标识。

## 7. 配置边界

`app/config.py` 使用 Pydantic Settings 管理：

- Provider 和 API 配置；
- 分块、检索和生成参数；
- Milvus URI、Token 和 Database；
- 上传限制；
- Web 监听地址；
- 日志格式、轮转和保留周期；
- Metrics 开关、地址和端口；
- Tracing 开关和 OTLP/HTTP endpoint。

Web 和 Metrics 默认监听 `127.0.0.1`。当前系统没有认证，不应直接监听公网地址。

## 8. 异常语义

- 检索基础设施异常继续向上传播，不伪装成“没有结果”；
- Generator 层不把 Provider 错误转换为成功文本；
- Web 层记录脱敏后的完整本地异常，只向用户返回通用错误；
- 流式生成异常不会重复追加用户消息；
- 子 Span 自动标记错误；被 Web 层捕获的异常会显式标记根 Span。
- 纯检索把空结果视为正常 200，把 stale/状态冲突映射为 409，把依赖或证据完整性故障映射为脱敏 503。

## 9. 当前边界

v1.7 在 v1.6.1 检索校准层上增加严格 Rewrite artifact、多查询 RRF、Cross-Encoder Reranker 和独立分数报告。v1.7.1 的四模式同配置对照显示三种增强模式质量相同，Rewrite 的尾延迟最低，组合模式没有额外质量收益。v1.8 将向量后端统一为 Milvus。v1.9/v1.9.1 增加 FastAPI/React 适配层、真实依赖探活、完整文档管理和浏览器回归。v2.0 在此基础上补齐统一 Compose、前后端镜像入口、基础 CI、演示脚本和发布文档。v2.0.1 规范化评测文本指纹并冻结当前确定性 Dense 基线；v2.0.2 在 Python CI Job 中实时生成报告、执行指标回归并上传 Artifact；v2.0.3 增加答案质量严格契约；v2.0.4 增加真实 Generator/Judge 装配、逐案例 Runner 和原子 JSON/Markdown 报告；v2.0.5 冻结 28 条答案质量 holdout、35 条阈值正负样本与 11 份专用语料；v2.0.6 使用固定 Ollama/DeepSeek 配置生成并人工复核旧 Prompt 对照；v2.0.7 只使用 validation 扫描 Dense L2 阈值，因正负 distance 明显重叠而冻结“不启用”决策；v2.0.8 加固不可信上下文 Prompt、统一 `[文档N]` 引用并增加流结束后的低基数观测；v2.1.0 新增单文档纯检索 API、证据哈希、active index 隔离和稳定错误语义；v2.2.0 增加检索超时/重试/并发策略、独立 readiness、跨服务 Trace Context 和 Chunk 级质量基线。评估层仍只依赖生产 Provider、`RAGGenerator` 和检索组件，生产 `app` 不反向依赖 `evaluation`。固定真实 Provider 评测结果不能外推为所有模型或用户语料的质量承诺。

```text
evaluation.runner / production_runner
├── evaluation.datasets       # v1.4 / v1.6 JSONL 黄金与 holdout 用例
├── evaluation.fingerprints   # UTF-8 BOM/换行规范化后的逻辑文本指纹
├── evaluation.baselines      # v2.0.1 当前确定性 Dense 回归基线
├── evaluation.rewrite_artifacts # 带 schema/Prompt/数据集指纹的 LLM 改写输入
├── evaluation.adapters       # Dense / BM25 / Hybrid / Rewrite / Rerank 边界
├── evaluation.metrics        # 纯函数检索/拒答指标
├── evaluation.answer_models  # 独立答案用例、Judge 和报告契约
├── evaluation.answer_adapters # Generator/Judge Protocol 与离线 Fake
├── evaluation.answer_metrics # 拒答和语义指标的固定分母聚合
├── evaluation.answer_reports # 转义后的原子 JSON/Markdown 答案报告
├── evaluation.answer_runner  # 真实 Provider 端到端答案评测 CLI
├── evaluation.threshold_calibration # 纯函数候选扫描、约束和决策模型
├── evaluation.threshold_runner # validation / holdout 协议 CLI
├── evaluation.datasets/v2_answer_quality # 答案/阈值数据集与合成 TXT 语料
├── evaluation.reports        # JSON/Markdown 报告与人工复核记录
├── evaluation.comparison     # 四模式同配置质量/延迟矩阵
└── evaluation.regression     # 基线比较和下降门禁
```

普通 PR CI 只执行确定性本地评测，不连接真实 Provider。真实 Ollama/云端报告仍是发布前人工证据，不进入每次 PR 的自动门禁。

答案 Runner 的 Generator 复用当前生产 `RAGGenerator` Prompt，Judge 使用独立抗注入 Prompt。v2.0.8 已完成生产 Prompt 加固、统一 `[文档N]` 输出和线上引用观测；Judge 仍与生产 Prompt 分离，避免评测指令反向进入线上生成。

当前仍不包含：

- Prometheus、Grafana、Jaeger 与 OpenTelemetry Collector 等可观测性后端容器；
- 历史感知检索，以及 Query Rewrite / Reranker 的 Web 默认接入；
- Celery/Redis 异步摄取；
- 认证、多租户、限流和生产高可用。

日志、指标、追踪和评测配置分别见[可观测性指南](OBSERVABILITY.md)与[评测指南](EVALUATION.md)。

## 存储维护约束

- 业务检索只选择 `record_type == "chunk"` 的记录，向量空间配置记录不得作为知识返回；非空 Collection 不允许混用 Embedding 模型或维度。
- 向量存储文本限制按 UTF-8 字节校验；过滤字段与值必须通过既有白名单和安全编码，不拼接不可信表达式。
