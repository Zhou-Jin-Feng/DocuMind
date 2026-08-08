# DocuMind - RAG 系统架构（v1.6.1）

## 1. 分层结构

```mermaid
flowchart TD
    UI["web_app.py / Gradio"] --> CFG["app.config / Settings"]
    CLI["app.lifecycle CLI"] --> REG["DocumentRegistry / SQLite"]
    CLI --> VS
    UI --> LC["DocumentLifecycleService"]
    LC --> REG
    LC --> LOAD["Document Loader"]
    LC --> CHUNK["Document Chunker"]
    LC --> EMB["Embedding Client"]
    LC --> VS["VectorStore / Chroma"]
    UI --> RET["Retriever"]
    RET --> EMB
    RET --> VS
    EVAL["evaluation runner"] --> RET
    EVAL --> LEX["BM25Retriever / jieba"]
    EVAL --> HYB["HybridRetriever / RRF"]
    HYB --> RET
    HYB --> LEX
    UI --> GEN["RAGGenerator"]
    GEN --> LLM["UniversalLLMClient"]
    UI --> OBS["app.observability"]
    RET --> OBS
    OBS --> LOG["JSONL Logs"]
    OBS --> MET["Prometheus Metrics"]
    OBS --> TRACE["OpenTelemetry Traces"]
```

`app/core` 保持业务能力，`app/observability` 提供横切能力。业务层只调用稳定封装，不直接依赖 Prometheus 注册表、OpenTelemetry 全局 Provider 或日志文件实现。

## 2. 文档索引流程

```text
上传校验
→ 内容哈希源文件持久化
→ Registry claim（no-op / indexing）
→ 文档加载与分块
→ 生成 index_id / 稳定 chunk_id
→ 批量 Embedding 和维度校验
→ Embedding 空间兼容校验
→ Chroma upsert / Chunk ID 收敛
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

`audit` 一次扫描 Chroma，报告旧索引、孤儿索引、缺失 active、active Chunk 数不一致和 v1.4 legacy Chunk。旧索引清理先落 `deleting`，再删除向量并落 `deleted`；进程在任一步中断后都可由下一次 `cleanup` 收敛。

`rebuild --dry-run` 不初始化 Embedding Provider，也不写入向量或状态。它先校验内容寻址源文件的 SHA-256，再用当前解析、分块和静态 Embedding 配置计算 planned fingerprint / `index_id`；Provider/模型未变化时复用注册表中已验证的真实维度，避免 Ollama 静态默认维度造成误判。

`rebuild --retry` 会在指定文档下寻找唯一的 `indexing` 目标。它既能恢复 active 索引的中断重建，也能恢复尚未切换 active 的新版本；没有目标或存在多个目标时拒绝猜测，配置已变化时要求恢复原配置或执行新的普通重建。

## 4. 问答流程

Web 默认问答链路保持 Dense-only：

```text
用户问题
→ Query Embedding
→ Chroma 距离检索
→ 最大距离阈值过滤
→ 构建带来源和页码的上下文
→ LLM 流式生成
→ UI 展示回答和引用来源
```

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

RRF 只使用名次，不直接比较 Chroma `distance` 与 BM25 原始分数。v1.6.1 使用 `dense_weight/(rrf_k+dense_rank) + lexical_weight/(rrf_k+lexical_rank)`，候选深度由 `candidate_multiplier` 控制；零权重通道不执行检索。BM25 可用 `lexical_score_threshold` 拒绝低分词法候选。结果分别保留 `distance`、`lexical_score`、`dense_rank`、`lexical_rank` 和 `fusion_score`，方便审计来源。词法候选没有向量距离时，UI 不显示伪造的距离值。

## 5. 可观测性架构

### 5.1 请求上下文

`contextvars` 保存 `request_id` 和 `trace_id`，支持同步生成器完整生命周期、嵌套恢复和异常清理。Tracing 开启后，当前 Span 的真实 Trace ID 会临时覆盖备用 Trace ID，使日志与 Trace 可关联。

### 5.2 日志

- 应用入口显式调用 `setup_logger()`；模块导入不创建文件。
- 控制台默认文本，文件默认 JSONL。
- 统一事件名、操作名、状态、数字耗时和异常类型。
- 日志 Patcher 负责字段补全和凭据脱敏。

### 5.3 Metrics

- `configure_metrics()` 只配置内存注册表。
- `start_metrics_server()` 只由 Web 主入口显式调用。
- 标签限制为 `provider`、`operation`、`status`、`error_type`。
- 关闭后所有操作 no-op，不监听端口。

### 5.4 Tracing

- 使用应用私有 `TracerProvider`，不覆盖 OpenTelemetry 全局 Provider。
- 默认关闭；没有 OTLP endpoint 时不创建网络 Exporter。
- Span 异常只记录 `error.type` 和 ERROR 状态，不发送默认异常事件。
- Span 属性过滤问题、Prompt、文档正文、文件名、凭据及高基数请求标识。

## 6. 配置边界

`app/config.py` 使用 Pydantic Settings 管理：

- Provider 和 API 配置；
- 分块、检索和生成参数；
- Chroma 数据目录；
- 上传限制；
- Web 监听地址；
- 日志格式、轮转和保留周期；
- Metrics 开关、地址和端口；
- Tracing 开关和 OTLP/HTTP endpoint。

Web 和 Metrics 默认监听 `127.0.0.1`。当前系统没有认证，不应直接监听公网地址。

## 7. 异常语义

- 检索基础设施异常继续向上传播，不伪装成“没有结果”；
- Generator 层不把 Provider 错误转换为成功文本；
- Web 层记录脱敏后的完整本地异常，只向用户返回通用错误；
- 流式生成异常不会重复追加用户消息；
- 子 Span 自动标记错误；被 Web 层捕获的异常会显式标记根 Span。

## 8. 当前边界

v1.6.1 在 v1.6 检索质量实验层上增加独立 holdout、按 split 汇总、真实 Provider 校准参数和门禁报告。评估层和生命周期层都不反向依赖 Web UI；虽然本地 Ollama holdout 校准通过，样本规模仍不足以自动改变 Web 默认 Dense-only 链路。

```text
evaluation.runner
├── evaluation.datasets       # v1.4 / v1.6 / v1.6.1 JSONL 黄金与 holdout 用例
├── evaluation.adapters       # Dense / BM25 / Hybrid 与 Fake Adapter 边界
├── evaluation.metrics        # 纯函数检索/拒答指标
├── evaluation.reports        # JSON/Markdown 报告
└── evaluation.regression     # 基线比较和下降门禁
```

当前仍不包含：

- Docker/Compose 和可观测性后端容器；
- 历史感知检索、Query Rewrite 和正式 Reranker；
- Celery/Redis 异步摄取；
- 认证、多租户、限流和生产高可用。

日志、指标、追踪和评估配置分别见 `OBSERVABILITY.md` 与 `EVALUATION.md`。
