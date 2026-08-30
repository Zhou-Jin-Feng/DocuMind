# DocuMind - RAG 评估

v1.4 引入了离线黄金数据集和回归测试运行器。它可以在不修改 Web 应用程序或调用真实 LLM 的情况下评估检索行为。v2.0.1 固化跨平台确定性基线，v2.0.2 将该基线接入普通 PR CI，v2.0.3 建立答案质量契约，v2.0.4 补齐真实 Provider Runner 和双格式报告入口，v2.0.5 冻结首套答案质量 holdout 与专用语料，v2.0.6 固化人工复核的旧 Prompt 真实对照，v2.0.7 完成 validation-only Dense L2 阈值校准并记录不启用决策，v2.0.8 完成生产 Prompt、引用和 Injection 加固对照。

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

### v2.0.3 答案质量评测契约

`evaluation/answer_models.py` 定义与旧 `EvaluationReport` 独立的 `AnswerQualityCase`、`GeneratedAnswer`、`JudgeResult`、`AnswerCaseEvaluation` 和 `AnswerEvaluationReport`。旧 `evaluation.models.AnswerResult` 仍只服务检索 Runner 的拒答/关键词冒烟，没有被扩展或替换。

数据集加载器强制检查完整字段集、重复 JSON 键、重复用例 ID、UTF-8、`train/validation/holdout` split、可回答/无答案字段约束，以及 `expected_document_ids` 与同级 `documents/*.txt` 文件名的对应关系。

Judge 输出必须是单个严格 JSON 对象，字段全集固定为四项 `0..1` 分数、`unsupported_claims`、`invalid_citations` 和 `reason`。重复键、额外/缺失字段、布尔值冒充数字、NaN/Infinity、Markdown 代码块和 JSON 前后附加文字都会直接失败，不做自由文本修复。

统一拒答文本为：

```text
根据提供的文档，未找到相关信息。
```

`outcome` 只允许 `answered/refused/no_context/error`：无检索结果时短路为 `no_context`，只有完整回答精确等于统一文本时才是 `refused`，不使用关键词猜测。指标聚合只对成功执行案例计算拒答准确率；四项 Judge 指标只纳入 `should_answer=true`、`outcome=answered` 且 Judge 成功的案例，并为每项指标单独记录分母。错误案例记录 `error_stage/error_type`，语义分数为 `null` 而不是 `0`。

`evaluation/answer_adapters.py` 中的 Generator/Judge Protocol 同时约束 Fake 和后续真实适配器。当前测试只使用内存映射，不初始化 Ollama、Milvus 或云端 LLM：

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_answer_evaluation.py -q
```

v2.0.3 验收时该独立文件为 `8 passed, 9 subtests passed`；全量 Python 回归为 `189 passed, 1 skipped, 20 subtests passed`，Vitest 为 `5 passed`，Playwright 为 `6 passed`。同时通过 Black、compileall、`pip check`、前端生产构建和 `deterministic_dense_v2` 检索回归门禁。

v2.0.3 阶段尚未实现真实 Runner、专用数据集或人工复核报告，因此当时只是离线评测基础。

### v2.0.4 真实答案 Runner

`evaluation/answer_runner.py` 按固定顺序执行每个案例：

```text
检索 -> 无上下文短路或生成 -> 确定性引用解析 -> Judge -> 聚合报告
```

检索为空时生成 `no_context`，不调用 Generator 或 Judge。检索、生成和 Judge 异常分别记录为 `retrieval/generation/judge` 阶段错误，只影响当前案例；Runner 继续处理剩余案例，失败内容不被伪装成拒答或 `0` 分。

真实 Generator 通过 `LLMAnswerGenerator` 直接桥接当前生产 `RAGGenerator` 的非流式入口，使用同一 System Prompt、上下文格式和默认温度 `0.7`。这是有意保留的旧 Prompt 行为，不能提前加入后续 Prompt Injection 防护，否则无法生成有效的 pre-hardening 对照。Judge 使用独立的 `LLMAnswerJudge`，明确把问题、上下文、参考答案和候选答案视为不可信数据；动态字段经 HTML 转义，编码规则计入 Judge Prompt 指纹，模型输出再交给 v2.0.3 的严格 JSON 解析器。

引用解析器当前只提取完整匹配 `\[文档([1-9]\d*)\]` 的标记，按首次出现顺序去重并记录 `citation_parser_version=bracketed-document-v1`。Judge Prompt 显式接收确定性解析结果，只允许精确 `[文档N]` 计为引用；若解析结果为空，两项引用分数必须为 0，代码会拒绝与此约束冲突的 Judge 输出。该规则只用于离线观测，不修改模型输出，也不改变 SSE 契约；统一线上引用格式仍属于后续 Prompt 加固任务。

`evaluation/answer_reports.py` 在同一文件系统中通过临时文件和替换写出完整 JSON/Markdown。Markdown 对问题、文档和模型文本做 HTML 转义，避免评测样本把报告结构当成可执行标记。报告记录数据集/语料指纹、Git 状态、Embedding/Chunk/检索配置、Generator/Judge 模型参数、两份 Prompt 指纹、拒答文本指纹和每项指标分母，不记录 API Key、认证头或 Milvus token。

CLI 示例：

```powershell
.\venv\Scripts\python.exe -m evaluation.answer_runner `
  --dataset path/to/dataset.jsonl `
  --documents-dir path/to/documents `
  --retrieval-mode dense `
  --embedding-provider ollama `
  --generator-provider openai `
  --generator-model gpt-4-turbo `
  --judge-provider openai `
  --judge-model gpt-4-turbo `
  --output-json evaluation/reports/answer-quality-current.json `
  --output-markdown evaluation/reports/answer-quality-current.md
```

退出语义固定为：`0` 表示所有案例成功且报告已写出；`1` 表示报告已写出但至少一个案例失败；`2` 表示输入、配置、Provider 初始化或报告路径错误。普通 PR CI 不调用真实 Provider。

答案契约与 Runner 的离线测试合计为 `15 passed, 12 subtests passed`，其中 BM25 CLI 集成测试使用注入的 Fake LLM 客户端验证真实装配、报告内容以及退出码 `0/1/2`，不连接云端模型、Ollama 或 Milvus。v2.0.4 全量 Python 回归为 `197 passed, 1 skipped, 23 subtests passed`，Vitest 为 `5 passed`，Playwright 为 `6 passed`；Black、compileall、`pip check`、TypeScript、前端生产构建和 `deterministic_dense_v2` 检索回归门禁均通过。

### v2.0.5 答案质量黄金集

`evaluation/datasets/v2_answer_quality/` 包含 11 份仓库内人工编写的 TXT 语料和 28 条 `holdout` 案例。首版配额冻结如下：

| 类别 | 数量 | 验证重点 |
|---|---:|---|
| `direct_fact` | 8 | 单文档事实和数值 |
| `multi_hop` | 5 | 两至三份文档的联合结论 |
| `no_answer` | 6 | 领域外、缺失值、错误前提和不存在的服务等级 |
| `insufficient_or_conflicting` | 3 | 候选日期、缺失 P95 和未决发布目标 |
| `prompt_injection` | 3 | 忽略规则、泄露 Prompt/密钥和停止引用等不可信指令 |
| `citation_boundary` | 3 | 同文档多事实和跨文档引用归属 |

所有问题、参考答案和原子 claim 均人工编写；不从生成模型自动扩写。可回答案例保留非空证据文档和逐项 claim，无答案与信息不足案例不保存参考答案，防止向 Judge 泄露虚构结论。Prompt Injection 语料使用独立文档和可识别的 `INJECTION_*` 哨兵，哨兵不得出现在参考答案或 claim 中。

黄金集审计测试固定验证总数、类别配额、全 `holdout` split、问题唯一性、原子 claim、多文档案例、全部语料被引用和注入哨兵边界。当前规范化文本指纹为：

```text
dataset_sha256  = f5eb00ddc448772e6369f8e2b8ae798cecf4736e2f7dc6619df49a728108055d
documents_sha256 = 7655501aca56852fd4db7755b8fea6512705b837cd070d5e9e00ad373a878103
```

`threshold_dataset.jsonl` 与答案集分离，使用旧检索 `GoldenCase` 契约。它包含 validation 5 个正样本和 15 个困难负样本，以及未参与选择的 holdout 5 个正样本和 10 个困难负样本；负样本集中覆盖主题相近但缺少日期、数值、负责人、模型名、恢复时长、授权例外和最终决策的提问，不使用纯领域外问题凑数。两个 split 的问题互不重复，也不与 28 条答案集完全重复；其规范化 SHA-256 为 `8853bf2aba5bc1266bd7202b6f7feb084a0fca242d475d6c2204928fdab12210`。

本阶段不调用 Ollama、Milvus 或云端 LLM，也不生成 pre-hardening 报告或扫描距离。28 条答案案例服务于下一阶段固定真实 Provider 的旧 Prompt 对照；35 条阈值案例只冻结 P0-2 的 validation/holdout 输入。阈值候选、distance 分布、一次性 holdout 结果和是否启用仍必须在后续独立任务中产生。因此“数据集已冻结”仍不等于“生产答案质量或拒答能力已经通过验收”，更不等于在线幻觉检测。

v2.0.5 数据集专项为 `8 passed, 101 subtests passed`，答案评测相关专项为 `32 passed, 113 subtests passed`，全量 Python 为 `205 passed, 1 skipped, 124 subtests passed`。Vitest 为 `5 passed`，Playwright 为 `6 passed`；Black、compileall、`pip check`、TypeScript、前端生产构建、两份 Compose、30 份 Markdown 静态检查和 `deterministic_dense_v2` 检索回归门禁均通过。BM25 诊断确认 28 条答案集中 19 个可回答案例、阈值集中 10 个正样本的全部标注文档均进入各自 Top-K；该结果只验证语料可检索性，不是生产 Embedding 质量结论。

### v2.0.6 旧 Prompt 真实对照

正式报告使用未加固的生产 `RAGGenerator` Prompt 和以下固定配置：

```text
Dataset: evaluation/datasets/v2_answer_quality/dataset.jsonl
Documents: evaluation/datasets/v2_answer_quality/documents
Retrieval: Dense, score_threshold=null, case Top-K=3/5
Embedding: ollama / qwen3-embedding / 4096
Chunk: 500 / 100
Generator: deepseek / deepseek-chat / temperature=0.7 / max_tokens=1000
Judge: deepseek / deepseek-chat / temperature=0.0 / max_tokens=1000
```

正式 JSON 与 Markdown 由同一次运行原子生成，分别保存在 `evaluation/reports/v2_answer_pre_hardening.json` 和 `.md`。人工复核记录为 `evaluation/reports/v2_answer_pre_hardening_review.md`。结果如下：

| 指标 | 分数 | 案例数 | 结论 |
|---|---:|---:|---|
| `successful_case_rate` | 1.0000 | 28 | 达到 1.00 |
| `refusal_accuracy` | 0.6786 | 28 | 低于 0.90 |
| `faithfulness` | 1.0000 | 19 | 高于 0.85 |
| `citation_correctness` | 0.0526 | 19 | 低于 0.85 |
| `citation_completeness` | 0.0526 | 19 | 低于 0.80 |
| `answer_relevance` | 1.0000 | 19 | 记录值，无硬门槛 |

28 条案例的标注文档全部进入 Top-K，19 条可回答答案经逐条核对均受证据支持。9 条负样本都表达了信息不足，但因为附带解释而不精确等于统一拒答文本，全部被严格契约判为 `answered`。19 条可回答答案中只有 1 条使用可解析的 `[文档N]`，其余只使用“文档1”或文件名。三条 Prompt Injection 均未输出哨兵、泄露 Prompt/凭据或服从恶意指令。

首轮候选曾暴露 Judge 在零解析引用时仍给引用满分的问题；修正 Judge 契约并补充一致性测试后才重新生成正式工件。报告如实记录父提交 `对应阶段源码快照` 与 `dirty=true`，因为评测器源码/测试改动和候选工件在正式运行前已经存在；候选工件随后删除，数据集、语料、生产 Prompt 和检索配置未发生变化。该工件是 Prompt 加固前的旧行为对照，不是达标的最终答案质量基线，也没有修改 Web 阈值、Prompt 或 SSE。

v2.0.6 验收结果为全量 Python `205 passed, 1 skipped, 124 subtests passed`、答案专项 `23 passed, 113 subtests passed`、Vitest `5 passed`、Playwright `6 passed`。Black、compileall、`pip check`、TypeScript、前端生产构建、两份 Compose、32 份 Markdown UTF-8/本地链接检查和 `deterministic_dense_v2` 回归门禁均通过。

### v2.0.7 Dense L2 阈值校准

`production_runner --split validation|holdout` 可以隔离冻结 split，并在报告中记录 `evaluation_split` 与 `distance_metric=L2`。`evaluation.threshold_runner scan` 只接受无阈值、Dense、baseline、L2 且数据集指纹一致的 validation 报告；它重新计算指标，不信任输入报告中的聚合值，只使用实际观测 distance 的相邻中点作为候选。固定选择规则是：先满足 Recall@3 下降不超过 `0.02`、无答案准确率不低于 `0.90`、成功率等于 `1.00`，再取数值最大的通过候选以尽量保留正常召回。

正式配置为 Ollama `qwen3-embedding`、4096 维、Dense、Milvus L2、Top-K=3、Chunk 500/100、11 份专用语料。validation 的 5 条正样本与 15 条困难负样本 20/20 成功；无阈值时正样本 Recall@3/MRR@3 均为 `1.0000`，无答案准确率为 `0.0000`。59 个候选全部失败：

| 候选 | Recall@3 | 无答案准确率 | 错误拒答率 | 结论 |
|---:|---:|---:|---:|---|
| `0.717509448528` | 0.4000 | 0.9333 | 0.6000 | 无答案目标通过，召回失败 |
| `0.752467751503` | 0.6000 | 0.9333 | 0.4000 | 无答案目标通过，召回失败 |
| `0.900638788939` | 1.0000 | 0.4667 | 0.0000 | 召回通过，无答案目标失败 |

正样本 Top-1 L2 范围为 `0.6420` 至 `0.8903`，困难负样本为 `0.7050` 至 `1.0464`，两者重叠明显。因为 validation 没有冻结候选，协议要求保持 holdout 未运行，不能查看 holdout 后再调约束。正式工件为 `v2_threshold_validation_raw.{json,md}`、`v2_threshold_validation_scan.{json,md}` 和 `v2_threshold_validation_review.md`；机器可读状态明确记录 `selected_threshold=null`、`holdout_status=not_run_no_validation_candidate` 与 `enable_reference_threshold=false`。

最终决策是 `Settings.retrieval_score_threshold=None` 和 `.env.example` 空值均保持不变。系统仍支持用户显式配置最大 L2 distance，但当前结果不能外推为 `qwen3-embedding`、参考部署或任意上传语料的推荐阈值，也不能声称 Web 已通过检索阈值实现可靠拒答。无上下文响应、Metrics、日志和 SSE 行为未修改。

v2.0.7 验收结果为全量 Python `215 passed, 1 skipped, 124 subtests passed`、阈值专项 `10 passed`、Vitest `5 passed`、Playwright `6 passed`。Black、compileall、`pip check`、TypeScript、前端生产构建、两份 Compose、35 份 Markdown UTF-8/本地链接检查、正式工件密钥扫描和 `deterministic_dense_v2` 回归门禁均通过。

### v2.0.8 Prompt、引用和注入防护

生产 `RAGGenerator` 保留 system/user 两消息结构，但在 system 规则中明确检索资料是不可信数据，忽略其中要求改规则、泄露 Prompt/凭据、调用工具或执行命令的文字。user 消息把问题包裹在 `<user_question>`，把资料包裹在 `<retrieved_context>`，每个资料块使用按检索列表位置生成的 `<document id="N" source="..." page="...">`。正文和属性统一 XML 转义，原文不能提前关闭边界；上游 rank 不连续时，公开 `sources.items[].rank` 仍按编排列表规范化为 1..N。

生产与离线评测共用 `app.core.citations` 的 `bracketed-document-v1` 解析器：只接受精确 `[文档N]`，保留首次出现顺序并去重；格式近似、自然语言来源和越界编号只作为非法诊断，不会被当作有效引用。SSE `status/sources/token/done/error` 事件及其字段没有改变，流结束后只在日志和 Metrics 中记录引用数量、非法数量和无引用状态，不记录答案或文档正文。

本阶段使用与 v2.0.6 相同的 Ollama `qwen3-embedding` 4096 维、DeepSeek `deepseek-chat` Generator/Judge、Dense、Milvus L2、空阈值、Chunk 500/100 和 28 条 holdout。最新干净提交上的 `temperature=0.7` hardened 报告成功率为 `1.0000`，拒答准确率 `0.7500`，Faithfulness、引用正确性、引用完整性和回答相关性均为 `0.9474`（19 条可回答 Judge 案例）；预先选定的 `temperature=0.1` 对照成功率为 `0.9643`、拒答准确率为 `0.7037`，已评估的四项质量指标均为 `1.0000`（17 条案例），但有 1 条案例在 Judge 阶段返回 `ValueError`。因此保留 `0.7`。旧 Prompt 的 Generator Prompt SHA 为 `513cd279f6f3cffdcacd2a0f92c892faad82075da7f1a0a9125c7f1ee1c8da17`，加固 SHA 为 `07c37d4a051fdf596de23b0480a5b866a1ee7341ed925982466a34f154ca3cdc`。

两份 hardened 报告各执行 3 条独立 Prompt Injection，均未输出 `INJECTION_*` 哨兵、system prompt、真实 API Key 或不存在的 `[文档99]`。低温对照连续三次均有 1 条 Judge 严格 JSON 解析失败；失败发生在评测 Judge，不是生成答案或 Injection 防护失败。JSON/Markdown 工件通过敏感模式扫描；逐案人工结论、运行环境、报告 SHA-256 和 `dirty=false` 状态见 [复核记录](../evaluation/reports/v2_answer_prompt_hardened_review.md)。

当前代码复审结果为 Python `220 passed, 1 skipped`，专项测试 `35 passed`，Vitest `5 passed`，Playwright `6 passed`；Black、compileall、`pip check`、TypeScript、前端生产构建、两份 Compose 配置解析、44 份 Markdown UTF-8/本地链接检查、5 份正式评测工件密钥模式扫描和 `deterministic_dense_v2` 回归门禁均通过。两份真实报告均在 `对应阶段源码快照` 干净提交上生成并记录 `dirty=false`。使用本机缓存基础镜像重建后的主 Compose API/前端均报告版本 `2.0.8` 并健康；真实冒烟完成 TXT 上传、可回答问题、无答案问题、`status -> sources -> token* -> done` SSE 事件、文档详情和删除闭环，删除后文档列表恢复为空。

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

### v2.2.0 P1 单文档纯检索契约基线

`evaluation/datasets/retrieve_quality_v1.json` 冻结两篇容易混淆的文档、6 个
Chunk 和 5 个单文档案例，其中包含 4 个可回答案例及 1 个阈值空结果案例。
`evaluation.retrieve_quality_runner` 使用仓库内 SHA-256 Token Embedding 和内存
向量存储，但检索入口是生产 `RetrievalService`；每个案例还会用同一过滤条件
直接调用底层 `Retriever`，以核验公共服务没有改变有序 Chunk ID。

生成当前报告：

```powershell
.\venv\Scripts\python.exe -m evaluation.retrieve_quality_runner `
  --json-output evaluation/reports/retrieve_quality_current.json `
  --markdown-output evaluation/reports/retrieve_quality_current.md
```

与签入基线执行回归门禁：

```powershell
.\venv\Scripts\python.exe -m evaluation.regression_runner `
  --baseline evaluation/baselines/retrieve_quality_v1.json `
  --current evaluation/reports/retrieve_quality_current.json `
  --allowed-drop ndcg_at_k=0 `
  --minimum api_bottom_parity_rate=1 `
  --minimum contamination_free_rate=1 `
  --minimum no_answer_empty_accuracy=1
```

冻结报告的 Recall@2、MRR@2、nDCG@2、空结果准确率、API/底层一致率、污染
清零率和成功率均为 `1.0`；Precision@2 为 `0.5`，因为每个正样本只标记一个
相关 Chunk，而 API 固定返回两个候选。Runner 会在逐案异常、公共/底层排序不一致、
跨文档污染或空结果错误时写出诊断报告并返回非零。报告记录数据集、文档、
Embedding、Schema、Retrieval、服务版本、Python 实现和操作系统指纹。

该报告只证明固定输入下纯检索契约与隔离行为可重复，不测量真实 Embedding、
Milvus、领域语义质量或线上延迟，也不能用于选择生产距离阈值。真实 Provider
结论必须使用隔离 Collection 和单独校准的数据集生成。

### P2-01 增强检索上线决策

P2-01 使用 `evaluation/datasets/v2_answer_quality/threshold_dataset.jsonl` 的
35 个冻结案例和 11 份合成语料，对 Dense、BM25、Hybrid 及
Hybrid + `BAAI/bge-reranker-base` 进行同输入真实对照。数据包含 20 个
validation 案例和 15 个 holdout 案例；最终决策只读取 holdout，其中 5 个可回答、
10 个困难无答案案例。Dense、Hybrid 和 Reranker 使用本地 Ollama
`qwen3-embedding`、4096 维向量和隔离 Milvus Collection；Reranker 使用 CPU
及本地模型缓存。所有临时 Collection 在报告生成后已删除。

候选门禁要求：至少 30 个总案例、15 个 validation、15 个 holdout，Recall、MRR
和无答案准确率不得低于 Dense，至少一项达到预先固定的最小收益，成功率为
`1.0`，且 P95 增量不超过 `750 ms`、倍数不超过 `2.0`。门禁还会校验四份报告
的案例指纹、数据集/语料指纹、分块、Embedding、阈值和 Hybrid 配置，并记录
每份源报告的 SHA-256。门禁还会从逐案结果重新计算 validation/holdout 的关键
质量、成功率和 P95 指标；报告内聚合值与逐案结果不一致时按无效证据拒绝。

| 模式 | Holdout Recall@3 | Holdout MRR@3 | Holdout 无答案 | Holdout P95 |
|---|---:|---:|---:|---:|
| Dense | 1.0000 | 1.0000 | 0.0000 | 163.6 ms |
| BM25 | 1.0000 | 1.0000 | 0.0000 | 0.6 ms |
| Hybrid | 1.0000 | 1.0000 | 0.0000 | 166.9 ms |
| Hybrid + Reranker | 1.0000 | 0.9000 | 0.0000 | 2237.6 ms |

运行决策器：

```powershell
.\venv\Scripts\python.exe -m evaluation.retrieval_candidate_gate_runner `
  --dense evaluation/reports/p2_1_ollama_threshold_dense.json `
  --bm25 evaluation/reports/p2_1_bm25_threshold.json `
  --hybrid evaluation/reports/p2_1_ollama_threshold_hybrid.json `
  --rerank evaluation/reports/p2_1_ollama_threshold_hybrid_rerank.json `
  --output-json evaluation/baselines/p2_retrieval_candidate_decision_v1.json `
  --output-markdown evaluation/baselines/p2_retrieval_candidate_decision_v1.md
```

退出码 `0` 表示至少一个候选满足 `GO`，`1` 表示证据有效但结论为 `NO_GO`，
`2` 表示报告无效或不可比较。本次正式结论为 `NO_GO`：在当前 11 Chunk、每份
语料基本只有一个 Chunk 且 5 条可回答 holdout 的 Dense Top-1 已为 `1.0` 的
天花板数据上，BM25 和 Hybrid 未观测到可计入门禁的质量收益；这不是对它们在
更大或更困难语料上“普遍无收益”的证明。Reranker 的 MRR 下降 `0.10`，P95
增加约 `2074 ms`、达到 Dense 的 `13.67` 倍。P2-01 因此按条件阶段关闭为 `DEFERRED`，公共 Schema `1.0`、
`dense-v1`、单文档范围和现有阈值行为均不改变。该结论只适用于冻结数据、
语料和本机运行环境；以后若更换代表性数据或候选配置，必须生成新的版本化决策，
不能覆盖本工件。

复审补充：四份报告的逐案诊断已写入决策工件的 `Diagnostic Signals`。Dense、
BM25 和 Hybrid 的可回答 Top-1 比例均为 `1.0`，因此 Recall/MRR 没有上升空间；
Reranker 有 1 条可回答案例从第 1 位降到第 2 位。四种模式对 10 条无答案案例均
返回非空候选（`candidate_no_answer_non_empty_rate=1.0`），这是因为本次对照明确
不带拒答阈值，不能解释为候选拒答能力相同。Reranker 的 holdout 单案例耗时范围
为 `1556.1–2533.7 ms`；首轮模型加载另在 validation 中形成冷启动长尾，热路径仍
远超 Dense，故延迟门禁失败并非统计误差。

### P2-01 DS-02 公开数据获取与试跑

DS-02 只获取 `evaluation/data_sources/manifest.json` 的
`download_authorization.source_ids` 白名单。下载器使用固定 revision、单线程、
`.part` Range 续传、三次退避、原子发布、逐文件大小/SHA-256 校验、20 GiB 总预算、
8 GiB 单来源上限和 120 GiB 最低空闲门禁。raw 与 normalized 数据均位于 Git 忽略的
`data/evaluation_sources/`。

安装开发/评测依赖后执行或复验下载：

```powershell
.\venv\Scripts\python.exe evaluation/data_source_downloader.py download
.\venv\Scripts\python.exe evaluation/data_source_downloader.py verify
```

真读取 Parquet/TSV 并运行有界本地 Embedding pilot：

```powershell
.\venv\Scripts\python.exe -m evaluation.data_source_validation `
  --read-rows-per-source 1000 `
  --embedding-sample-size 32 `
  --embedding-batch-size 8 `
  --output-json evaluation/reports/p2_ds02_acquisition_evidence_v1.json `
  --output-markdown evaluation/reports/p2_ds02_acquisition_evidence_v1.md
```

本次 12 个文件共 169,682,657 bytes，T2Ranking dev、BEIR NFCorpus 与 BEIR
SciFact 的大小、哈希、字段和行数全部通过。3,000 行有界读取完成；32 条 T2 中文
passage 使用 `qwen3-embedding`、batch 8、4096 维，最近一次政策刷新复跑测得约
2.96 passage/s。

MIRACL 全量下载/建库结论为 `DEFER_FULL_DOWNLOAD`。其 Embedding-only 方向性
外推约 462.6 小时，超过 18 小时启动线约 25.7 倍、超过 24 小时硬上限约 19.3
倍；raw float32 向量约 80.8 GB，
还会在计算 Milvus index/WAL 前突破 120 GiB 空闲下限，且许可证来源冲突尚未解决。
只有先冻结不需要全量 Dense 建库的确定性子集或 hard-negative 协议、解决许可证，
并证明端到端预计不超过 18 小时、实际运行硬停不超过 24 小时且磁盘满足下限，才能
重新申请 MIRACL。端到端计时覆盖下载、标准化、Embedding、Milvus 写入/建索引、
检索与 Reranker 评测、报告生成和清理。

### P2-01 DS-03 确定性规范化

DS-03 将 T2Ranking dev、BEIR NFCorpus 和 BEIR SciFact 的官方 corpus、query、qrels
转换为严格版本化的 `documents.jsonl`、`queries.jsonl`、`qrels.jsonl` 和根
`snapshot.json`。四份 JSON Schema 位于 `evaluation/data_sources/contracts/`，
适配器与 CLI 位于 `evaluation/data_source_normalization.py`，详细字段和边界见
`evaluation/data_sources/README.md`。

```powershell
.\venv\Scripts\python.exe -m evaluation.data_source_normalization build `
  --report-json evaluation/reports/p2_ds03_normalization_evidence_v1.json `
  --report-markdown evaluation/reports/p2_ds03_normalization_evidence_v1.md

.\venv\Scripts\python.exe -m evaluation.data_source_normalization validate
```

非空目标目录默认拒绝覆盖；只有显式 `--replace` 且旧目录包含有效 DS-03
`snapshot.json` 归属标记时才允许原子替换。构建器会拒绝重复 ID/qrels、悬空引用、
跨 split 查询、`0-3` 外相关性等级和路径穿越。规范化只移除 BOM、统一换行，不猜测
或修复上游文本编码。

本次产出 127,421 份文档、27,158 条查询、254,484 条 qrels；独立临时目录重建的
`snapshot.json` 与九个 JSONL 文件全部逐字节一致，聚合数据指纹为
`05096037d6cdd2ae9667e66616ae1f55c8236383f0a72f559f4f1846618fbaaa`。T2 原始语料中
23/118,605 个 document 行含 Unicode replacement character，查询为 0/22,812；
该上游局部缺陷被原样保留并须在后续评测中显式审计。

本阶段没有下载新数据、运行 Embedding、写入 Milvus、调用生成模型或改变公共
`/api/v1/retrieve`、Schema `1.0`、`dense-v1` 和单文档范围。

### P2-01 DS-04 代表性数据集

DS-04 在 `evaluation/datasets/p2_retrieval_v2/` 生成完全合成且可提交的 Track B
材料。25 个 DocuMind 运维主题各包含 active、draft、superseded 三个版本，共 75
份文档；全部使用生产 `chunk_size=500`、`chunk_overlap=100` 的递归分块器，得到
235 个 Chunk，每份文档 3 至 4 个 Chunk，中位数为 3。主题覆盖上传、解析、分块、
Embedding、生命周期、检索、健康、可观测性、存储和安全，不包含客户或生产文档。

```powershell
.\venv\Scripts\python.exe -m evaluation.representative_dataset build `
  --replace `
  --report-json evaluation/reports/p2_ds04_pre_review_v1.json `
  --report-markdown evaluation/reports/p2_ds04_pre_review_v1.md

.\venv\Scripts\python.exe -m evaluation.representative_dataset validate

.\venv\Scripts\python.exe -m evaluation.representative_dataset finalize `
  --report-json evaluation/reports/p2_ds04_final_review_v1.json `
  --report-markdown evaluation/reports/p2_ds04_final_review_v1.md
```

探索池为 400 题，自动预选 100 题候选，proposed validation/holdout 各 50 题、各
13 题无答案。候选主类别配额为 exact lexical 15、semantic 15、difficult negative
20、authority/version 10、non-plain-text 10、general operations 30。每个 qrel 都绑定
同一文档内的生产 Chunk ID、证据控制项、原文引句和 `0-3` grade；验证器会重跑生产
分块器并拒绝跨文档 qrel、缺失引文、重复问题、指纹漂移和未归属目录替换。

人工审查前数据集指纹为
`0a4d2b7d036185335f2cf13b9a226ead7ccdbd47b6dff4adb02b4d9a687d330d`，自动隐私/
凭据扫描 0 命中。`review_batch_1.md` 和 `review_batch_2.md` 各含 50 题，并展示源
文件、document ID、chunk ID、grade 与引文；审查包哈希也纳入快照。

人工审查结果已经固化：94 题 `approve`，6 题 `modify`，0 题 `delete`，0 题
`pending`。6 个修改均为用户明确指定的 superseded qrel grade `2 -> 3`，修改目标、
旧值和新值保存在 `review_decisions.jsonl`。正式 `gold_dataset.jsonl` 保留 100 题，
每题的 answerability、qrels、grade、歧义、权威和隐私状态均标记为人工确认；最终数据集
指纹为
`7f2440695b6f575be045e066544009a765a308544982adb8618bf5004bf418a3`，证据报告见
`evaluation/reports/p2_ds04_final_review_v1.{json,md}`。本 gold 随后已通过 DS-05
隔离审计并冻结，具体见下一节；在 DS-06 完成前不用于生产收益声明。

### P2-01 DS-05 Split 隔离与指纹冻结

DS-05 在任何 Embedding、Milvus 或模式评测之前，对 DS-04 的正式
`gold_dataset.jsonl` 执行 split 隔离和泄漏审计，并将结果冻结到
`evaluation/datasets/p2_retrieval_v2/split_freeze.json`。机器可读审计与脱敏
报告分别为 `evaluation/reports/p2_ds05_split_audit_v1.json` 和 `.md`。

validation 与 holdout 各 50 题、各 6 个主题族；两者之间的 case ID、规范化问题、
事实族、主题、文档、生产 Chunk、qrel pair、证据控制项和证据引句哈希均为零重合。
问题相似度扫描固定使用 NFKC、casefold、仅保留字母数字的规范化，以及
`SequenceMatcher >= 0.95` 的高置信阈值，跨 split 近重复为 0。冻结文件同时记录每题
身份、问题集合、qrel pair 集合和记录集合 SHA-256；之后修改 gold 或移动 split 会在
评测前被拒绝。

```powershell
.\venv\Scripts\python.exe -m evaluation.representative_split_audit audit
.\venv\Scripts\python.exe -m evaluation.representative_split_audit freeze
.\venv\Scripts\python.exe -m evaluation.representative_split_audit validate
```

DS-05 冻结 SHA-256 为
`49600e59d3525ac78ffadb61f667004db42752e0b80ad1bccce4e383ae4472a2`；审计 SHA-256
为 `eb380f920044ecb0878ed56551222a5e5aca7bddce0ebf9cf845e1eee866d93b`。DS-05
本身不运行四模式指标，也不改变 `/api/v1/retrieve`、Schema `1.0`、`dense-v1` 或
单文档范围；冻结结果随后作为 DS-06 的唯一输入。

### P2-01 DS-06 四模式评测与第二次冻结候选

DS-06 在 75 份代表性文档、235 个生产 Chunk 和 50/50 validation/holdout 上完成
真实 Dense、BM25、Hybrid 与 CPU `BAAI/bge-reranker-base` 对照。Reranker Top-5
只在 validation 选择，holdout 只执行一次。最终报告为
`evaluation/reports/p2_ds06_final_decision_v1.{json,md}`，结论为
`PASS WITH NOTES / NO_GO`。

| 模式 | Recall@3 | MRR@3 | nDCG@3 | P95 | 结论 |
|---|---:|---:|---:|---:|---|
| Dense | 0.4054 | 0.3018 | 0.3278 | 170.3 ms | baseline |
| BM25 | 0.3243 | 0.2477 | 0.2564 | 7.9 ms | 质量回退 |
| Hybrid | 0.3919 | 0.3153 | 0.3234 | 186.8 ms | Recall/nDCG 回退 |
| Reranker Top-5 | 0.4459 | 0.4459 | 0.4360 | 1102.9 ms | 质量提升但延迟不合格 |

本次评测证明 Reranker 在代表性多 Chunk 语料上有质量信号，但 P95 约为 Dense 的
`6.48x`，超过 `+750 ms` 和 `2x` 门禁；BM25 和 Hybrid 不能作为默认替代。四种模式
均未配置冻结的拒答策略，no-answer 空结果率为 0 不代表具备拒答能力。增强方案保留为
离线/受控实验，不改变线上公共契约。

第二次项目冻结候选是“个人项目级冻结”，不是公网生产认证：它固定 v2.2.0 Dense
基线、P2 数据证据、评测报告、测试和边界文档；不包含 raw 数据、模型缓存、Milvus
数据、`agent/` 工作资料或临时产物。当前报告生成于最终提交前的工作树，提交时必须
保持输入和报告字节不变，并在提交后复核哈希；按 holdout 一次性规则，不重复运行同一
holdout。

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

当前 v2.2.0 仍将查询重写、BM25/Hybrid 和交叉编码器重排序保留在公共请求路径之外。Docker Compose 已覆盖 FastAPI、React、Milvus、etcd 和 MinIO；Prometheus/Grafana/Jaeger 等完整可观测性后端、Celery/Redis、身份验证、在线历史感知检索和生产发布策略仍是后续路线图项目。旧 Prompt 对照、阈值校准和 Prompt/引用加固均已完成；阈值结论是不启用，P2-01 增强检索结论为 `NO_GO`，答案质量和检索候选结果只适用于各自固定数据集、语料和 Provider 配置。
