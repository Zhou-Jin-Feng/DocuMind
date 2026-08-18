# DocuMind - RAG 评估

v1.4 引入了离线黄金数据集和回归测试运行器。它可以在不修改 Web 应用程序或调用真实 LLM 的情况下评估检索行为。v2.0.1 固化跨平台确定性基线，v2.0.2 将该基线接入普通 PR CI。

## 数据集

默认数据集是 `evaluation/datasets/golden_dataset.jsonl`。每个非空行都是一个严格的 JSON 对象：

```json
{
  "id": "rag-core-components",
  "question": "RAG 系统包含哪些核心组件？",
  "expected_document_ids": ["knowledge-base"],
  "expected_keywords": ["文档加载", "分块", "向量数据库", "检索", "生成"],
  "should_answer": true,
  "top_k": 3,
  "category": "exact_term"
}
```

`expected_document_ids` 是一个逻辑文档标识符。真实的适配器必须通过 `metadata.document_id` 暴露相同的稳定值；文件名和绝对路径不是评估标识符。

无答案案例使用空的 `expected_document_ids` 列表和 `should_answer: false`：

```json
{"id":"rag-out-of-scope","question":"明天股票会涨吗？","expected_document_ids":[],"expected_keywords":[],"should_answer":false,"top_k":3}
```

`category` 对于旧数据集是可选的，默认为 `general`。v1.6 数据集使用 `exact_term`、`semantic_paraphrase`、`keyword_precision`、`hard_negative`、`multi_hop` 和 `no_answer`；报告为每个类别包含单独的指标表。

`split` 也是可选的，为了向后兼容默认为 `all`。支持的值有 `all`、`train`、`validation` 和 `holdout`。报告按类别和拆分聚合相同的指标。v1.6.1 的保留测试案例位于 `evaluation/datasets/v1_6/holdout_dataset.jsonl`；将它们与调优案例分开，并用于最终校准检查。

## 指标

运行器报告以下指标：

- `recall_at_k`：在 Top-K 中找到的预期文档数除以预期文档总数；
- `precision_at_k`：Top-K 中唯一相关文档 ID 数除以 K；来自同一文档的多个块只计算一次；
- `mrr_at_k`：第一个相关文档的倒数排名；
- `top_k_hit_rate`：至少有一个预期文档在 Top-K 中的可回答案例比率；
- `correct_document_avg_rank`：第一个相关文档的平均排名；
- `no_answer_retrieval_accuracy`：返回零个 Top-K 文档的无答案案例比率；
- `refusal_accuracy`：`should_answer` 与答案适配器之间的一致性；
- `keyword_coverage`：当答案适配器返回文本时的预期关键词覆盖率；
- `successful_case_rate`、`average_duration_ms`、`p50_duration_ms`、
  `p95_duration_ms` 和 `maximum_duration_ms`。

无答案案例被排除在正向目标检索指标之外，因为它们没有相关的文档 ID。它们包含在 `no_answer_retrieval_accuracy` 中；在没有距离阈值的情况下，向量存储通常会返回一个不相关的最近文档，此指标会暴露该行为。当配置了答案适配器时，它们仍包含在拒绝准确率中。

## 离线演示

在不需要 Ollama、Milvus、网络访问或 LLM 的情况下运行确定性演示：

```powershell
.\venv\Scripts\python.exe -m evaluation.runner `
  --dataset evaluation/datasets/golden_dataset.jsonl `
  --retrieval-mode dense `
  --output-json evaluation/reports/current-deterministic.json `
  --output-markdown evaluation/reports/current-deterministic.md
```

默认演示加载示例文档，并通过确定性哈希嵌入和内存向量存储来测试生产环境的 `Retriever`。可回答性适配器保持虚拟状态。该演示是有意设计为确定性的：其目的是验证真实的检索边界、数据集解析、报告生成和评估流程，而不是声称生产检索质量。

### v2.0.1 确定性基线与文本指纹

当前 CI 比较基线是 `evaluation/baselines/deterministic_dense_v2.json`，对应的人类可读报告是 `evaluation/baselines/deterministic_dense_v2.md`。旧 `evaluation/baselines/demo_baseline.json` 只保留为 v2.0 历史产物，其 metadata 与当前 Runner 不兼容，不得用于新的 CI。

评测文本使用逻辑内容指纹：读取 UTF-8 文本后移除开头 BOM，并把 CRLF 和 CR 统一为 LF，再计算 SHA-256。语料指纹同时覆盖相对文件名和规范化正文，因此换行风格不会造成 Windows/Linux 假不兼容，正文或文件名的真实变化仍会改变指纹。`file_sha256()` 保留原始字节语义，只用于确实需要字节级身份的场景。

当前基线的复核事实：

| 项目 | 值 |
|---|---|
| 数据集指纹 | `81741dfc4e4a59698b45ba2565558203aa0f7906c077f98749eb88ce512019a6` |
| 语料指纹 | `645e477edbcd6086226621abb76ddfa147b44acf56c632edf39e89e8220298b3` |
| 案例 | 8 条，全部执行成功 |
| Recall@3 | `0.8333` |
| No-answer retrieval accuracy | `0.0` |

这些指标是回归起点，不是质量目标。尤其是 `no_answer_retrieval_accuracy=0.0`，只说明无阈值 Dense 检索仍会返回最近候选，后续必须用更大的困难负样本集单独校准阈值。

### v2.0.2 PR CI 质量门禁

`.github/workflows/ci.yml` 的 Python Job 在单元测试后实时运行：

```bash
python -m evaluation.runner \
  --dataset evaluation/datasets/golden_dataset.jsonl \
  --retrieval-mode dense \
  --output-json "${{ runner.temp }}/rag-evaluation/current-evaluation.json" \
  --output-markdown "${{ runner.temp }}/rag-evaluation/current-evaluation.md"

python -m evaluation.regression_runner \
  --baseline evaluation/baselines/deterministic_dense_v2.json \
  --current "${{ runner.temp }}/rag-evaluation/current-evaluation.json"
```

这条路径只使用仓库内 JSONL/TXT、确定性哈希 Embedding 和内存向量存储，不连接 Ollama、Milvus、Hugging Face 或付费 LLM。JSON/Markdown 实时报告使用 `actions/upload-artifact@v4` 和 `if: always()` 上传，保留 14 天；生成文件位于 GitHub Runner 临时目录，不提交回仓库。

受控故障验证保留了全部配置和输入指纹，只把当前报告的 `recall_at_k` 从 `0.8333` 降到 `0.7`。`regression_runner` 返回 `FAIL` 和退出码 `1`；恢复原报告后返回 `PASS`。因此验证的是实际指标回退，而不是用不兼容指纹制造失败。

### v1.6 检索对比

扩展的数据集存储在 `evaluation/datasets/v1_6/` 中，包含 9 个工程文档的 32 个案例。使用 `--retrieval-mode dense`、`bm25` 或 `hybrid` 运行三种确定性对比。已签入的报告是 `evaluation/reports/v1_6_{dense,bm25,hybrid}.{json,md}`。

| 模式 | Recall@3 | MRR@3 | 命中率 | 无答案准确率 |
|---|---:|---:|---:|---:|
| Dense 哈希冒烟测试 | 0.2593 | 0.1173 | 0.2593 | 0.0000 |
| 仅 BM25 | 0.9630 | 0.9012 | 0.9630 | 0.0000 |
| 等权重 RRF | 0.5556 | 0.4136 | 0.5556 | 0.0000 |

哈希 Dense 后端是有意简化的，不是生产语义模型。等权重 RRF 比 Dense 冒烟测试有所改进，但表现不如 BM25，因为弱 Dense 排名仍然同等贡献。这证明应该使用预期的真实嵌入模型运行相同的对比，而不是针对小型固定集调整权重或切换 Web 默认值的证据。所有未设置阈值的模式仍会为无答案问题强制返回一些不相关的候选项，因此弃权阈值需要单独校准。

生产基线 CLI 接受相同的模式：

```powershell
.\venv\Scripts\python.exe -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/golden_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --retrieval-mode hybrid `
  --provider ollama
```

仅 BM25 不调用嵌入提供程序并拒绝 `--score-threshold`。Hybrid 使用 RRF 排名，从不直接比较 Milvus L2 距离与 BM25 分数。

### v1.6.1 检索校准

v1.6.1 添加了一个单独的 12 案例保留集，并使 Hybrid 校准明确化。CLI 选项包括：

- `--dense-weight` 和 `--lexical-weight`：非负 RRF 通道权重；它们不能同时为零；
- `--rrf-k`：正 RRF 平滑常数；
- `--candidate-multiplier`：正候选深度乘数；
- `--score-threshold`：最大可接受的 Dense 距离；
- `--lexical-score-threshold`：最小可接受的 BM25 分数。

所有值都会写入报告元数据。权重为零的通道不会被查询。Web 应用程序保持仅 Dense 模式，不使用这些实验性设置。

已签入的真实提供程序报告使用本地 Ollama `qwen3-embedding`（4096 维）、9 个文档、10 个生产块和 12 个保留案例：

| 模式 | Recall@3 | MRR@3 | 无答案准确率 | 结果 |
|---|---:|---:|---:|---|
| Dense，无阈值 | 1.0000 | 1.0000 | 0.0000 | 基线 |
| BM25，无阈值 | 1.0000 | 0.9394 | 0.0000 | 基线 |
| 等权重 Hybrid，无阈值 | 1.0000 | 1.0000 | 0.0000 | 基线 |
| Dense，距离 <= 1.0 | 1.0000 | 1.0000 | 1.0000 | 已校准候选 |
| Hybrid，距离 <= 1.0 且 BM25 >= 12.2 | 1.0000 | 0.9545 | 1.0000 | 已校准候选 |

运行已校准的 Hybrid 候选及其保留门控：

```powershell
.\venv\Scripts\python.exe -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2 `
  --dense-weight 1.0 --lexical-weight 1.0 `
  --rrf-k 60 --candidate-multiplier 5

.\venv\Scripts\python.exe -m evaluation.regression_runner `
  --baseline evaluation/reports/v1_6_1_ollama_holdout_hybrid.json `
  --current evaluation/reports/v1_6_1_ollama_holdout_hybrid_calibrated.json `
  --allowed-drop mrr_at_k=0.05 `
  --minimum recall_at_k=1.0 `
  --minimum no_answer_retrieval_accuracy=1.0 `
  --minimum successful_case_rate=1.0
```

这些阈值是针对此固定语料库校准的证据，而非在线默认值。在更改语料库、分块、提供程序、模型或距离度量后重新验证它们。

对于真实基线，用支持预期嵌入模型和向量集合的真实 `RetrieverAdapter` 替换确定性集成组件。在比较更改时保持相同的文档 ID 和黄金数据集。

可重用的生产接线由 `build_configured_retrieval_adapter()` 暴露。它使用配置的真实嵌入提供程序、生产分块器、Milvus `VectorStore` 和生产 `Retriever`。调用它可能会联系 Milvus、Ollama 或云 API，应该在创建基线时谨慎执行。

使用 CLI 创建真实的仅检索基线。该命令不调用 LLM，因此答案生成指标保持 `N/A`：

```powershell
.\venv\Scripts\python.exe -m evaluation.production_runner `
  --provider ollama `
  --milvus-uri http://127.0.0.1:19530 `
  --collection-name rag_evaluation
```

CLI 在退出前显式释放 Milvus 适配器。使用与应用程序索引分离的 Collection。

### 当前 Ollama 基线

已签入的 Ollama 报告是使用 `qwen3-embedding`（4096 维）、5 个简短固定文档和 8 个案例生成的：6 个可回答问题和 2 个无答案问题。这些是真实的本地 Ollama 调用，但数据集是一个小型工程基线，而不是统计上代表性的生产证据。

在没有距离阈值的情况下，6 个可回答案例都将其目标文档放在排名 1（`Recall@3=1.0`，`MRR@3=1.0`），而两个无答案案例仍然返回不相关的最近文档（`no_answer_retrieval_accuracy=0.0`）。`Precision@3=0.3333` 是预期的，因为每个可回答案例标记一个相关文档，而检索器返回三个。`successful_case_rate=1.0` 表示所有调用都成功完成而没有异常；它不是答案质量分数。

使用实验性最大距离阈值 `1.0`，相同样本保持 `Recall@3=1.0` 并将 `no_answer_retrieval_accuracy` 提高到 `1.0`。此阈值只是从两个负面示例派生的候选值。在数据集包含更多真实文档、释义、困难负样本和特定领域的无答案问题之前，它不能成为在线默认值。

报告记录了提供程序、模型、实际向量维度、块设置、Top-K 值、阈值和数据集大小。本地延迟是硬件快照，应仅在相同机器和服务条件下进行比较。

## v1.7 查询重写和重排序器

v1.7 保持 Web 应用程序不变，并引入了两个仅用于评估的阶段：

- 查询重写始终保留标准化的原始问题作为第一个查询。LLM 响应必须是一个严格的 JSON 对象，`{"queries":[...]}`；空、重复、markdown 包装或额外字段的响应会使案例失败，而不是静默更改检索行为。
- 多查询检索独立运行每个查询，仅通过稳定的 `metadata.chunk_id` 去重，并在排名上使用第二个 RRF 层。它不会跨查询比较原始分数。
- 交叉编码器重排序接收扩展的候选集，并写入 `rerank_score`，而不替换 `distance`、`lexical_score`、Hybrid `fusion_score` 或 Query RRF `query_fusion_score`。

`evaluation.rewrite_runner` 将外部 LLM 生成与检索评估分离。它创建一个严格的、版本化的工件，包含提供程序、模型、生成参数、提示 SHA-256、数据集 SHA-256 以及每个问题的替代方案。`evaluation.production_runner --rewrite-map` 拒绝具有不同数据集指纹、问题集、不支持的架构版本或请求的重写计数超过工件生成限制的工件，因此后续的本地运行在其 LLM 输入方面是确定性的。

```powershell
python -m evaluation.rewrite_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --provider deepseek --model deepseek-chat `
  --max-rewrites 2 `
  --max-tokens 256 `
  --output evaluation/datasets/v1_7/holdout_rewrites_deepseek.json

python -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2 `
  --enhancement-mode rewrite `
  --rewrite-map evaluation/datasets/v1_7/holdout_rewrites_deepseek.json
```

生产运行器支持 `baseline`、`rewrite`、`rerank` 和 `rewrite-rerank` 模式。每个报告都记录增强模式和所有启用阶段的参数。可以使用 `--reranker-local-files-only` 强制缓存的交叉编码器离线运行，这可以防止在受限环境中进行每案例 Hugging Face 元数据检查。

```powershell
python -m evaluation.production_runner `
  --dataset evaluation/datasets/v1_6/holdout_dataset.jsonl `
  --documents-dir evaluation/datasets/v1_6/documents `
  --provider ollama --retrieval-mode hybrid `
  --score-threshold 1.0 --lexical-score-threshold 12.2 `
  --enhancement-mode rerank `
  --reranker-model BAAI/bge-reranker-base `
  --reranker-batch-size 8 --reranker-device cpu `
  --reranker-local-files-only
```

原始 v1.7.0 重排序报告使用本地 Ollama `qwen3-embedding`、CPU 上的 `BAAI/bge-reranker-base`、相同的 12 案例保留集和已校准的 Hybrid 基线：

| 模式 | Recall@3 | MRR@3 | 无答案准确率 | 成功率 | 平均时长 |
|---|---:|---:|---:|---:|---:|
| v1.6.1 已校准 Hybrid | 1.0000 | 0.9545 | 1.0000 | 1.0000 | 420.7 ms |
| v1.7 已校准 Hybrid + 重排序器 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 937.9 ms |

重排序器修复了观察到的排名错误，但在此 CPU 上增加了约 517.2 ms。这一历史单模式结果促成了下面完整的 v1.7.1 比较；它并未授权 Web 默认更改。

v1.7.1 使用延迟百分位数重新生成所有四个报告。在单个回归门控通过后，创建一个严格的比较工件。该比较拒绝缺失的模式、错误的 `enhancement_mode` 标签或对数据集、语料库、嵌入、分块、检索、阈值和 Hybrid 配置的更改：

```powershell
python -m evaluation.comparison_runner `
  --baseline evaluation/reports/v1_7_1_ollama_holdout_hybrid_baseline.json `
  --rewrite evaluation/reports/v1_7_1_ollama_holdout_hybrid_rewrite.json `
  --rerank evaluation/reports/v1_7_1_ollama_holdout_hybrid_rerank.json `
  --rewrite-rerank evaluation/reports/v1_7_1_ollama_holdout_hybrid_rewrite_rerank.json
```

JSON 比较存储每个模式的指标和 `模式 - 基线` 增量。质量和延迟保持分离，而不是折叠成一个主观分数。P50/P95/max 包括懒加载模型，因此第一案例冷启动成本保持可见。

最终的 v1.7.1 运行产生了以下相同配置的结果：

| 模式 | Recall@3 | Precision@3 | MRR@3 | 无答案 | 平均 ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 基线 | 1.0000 | 0.3333 | 0.9545 | 1.0000 | 308.3 | 308.7 | 325.7 |
| 重写 | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 890.2 | 878.5 | 961.4 |
| 重排序 | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 1018.9 | 690.0 | 2462.0 |
| 重写-重排序 | 1.0000 | 0.3333 | 1.0000 | 1.0000 | 1742.6 | 1674.4 | 2608.7 |

所有三种增强模式都修复了相同的单个基线排名错误并通过了回归门控。重写是后续有界集成实验的首选候选，因为它以显著更低的 P95 延迟匹配重排序质量。组合模式增加了延迟而没有测量到的质量提升，应保持禁用状态。12 案例保留集太小，不能单独更改 Web 默认值。

## 回归门控

在 Python 中将当前报告与保存的基线进行比较：

```python
from evaluation.models import EvaluationReport
from evaluation.regression import RegressionGate

gate = RegressionGate(
    allowed_drops={"recall_at_k": 0.02, "mrr_at_k": 0.02},
    minimums={"successful_case_rate": 1.0},
)
result = gate.evaluate(baseline_report, current_report)
result.assert_passed()
```

门控使用绝对指标下降。当基线具有数值时，缺失当前指标会失败；在两个报告中都不适用的指标会被跳过。

针对两个 JSON 报告运行自动 CLI 门控：

```powershell
.\venv\Scripts\python.exe -m evaluation.regression_runner `
  --baseline evaluation/baselines/deterministic_dense_v2.json `
  --current evaluation/reports/current-deterministic.json
```

默认策略允许 Recall、Precision、MRR 和 Top-K 命中率的绝对下降为 `0.02`，不允许无答案检索准确率下降，并要求 `successful_case_rate=1.0`。使用重复的 `--allowed-drop METRIC=VALUE` 和 `--minimum METRIC=VALUE` 参数来覆盖或添加规则。`--no-default-policy` 禁用内置规则。

退出代码对于本地脚本和 CI 是稳定的：`0` 表示通过，`1` 表示质量回归，`2` 表示无效输入或不兼容的报告。在检查指标之前，CLI 要求匹配数据集名称、Top-K、案例计数、黄金数据集 SHA-256、文档语料库 SHA-256 以及每个共享的嵌入、分块、阈值、检索和 Hybrid 配置字段。有意更改这些输入的报告属于校准比较，而不是回归门控。重复的 JSON 键在比较前会被拒绝。

`correct_document_avg_rank` 有意不在默认策略中，因为较低的值更好；当前的 `allowed-drop` 策略仅适用于较大值更好的指标。

## 范围

当前 v2.0.2 仍将查询重写和交叉编码器重排序保留在 Web 默认请求路径之外。Docker Compose 已覆盖 FastAPI、React、Milvus、etcd 和 MinIO；Prometheus/Grafana/Jaeger 等完整可观测性后端、Celery/Redis、身份验证、在线历史感知检索和生产发布策略仍是后续路线图项目。
