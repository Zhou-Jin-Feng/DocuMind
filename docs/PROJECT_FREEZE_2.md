# DocuMind 2.2.0 交付范围与验证候选

状态：`READY FOR FREEZE / PASS WITH NOTES`

本文记录已验证的交付范围，不是公网多租户生产认证。系统为
可运行、可复现、工程可信的本地单用户或可信私网 RAG 服务，并作为 ScholarTrace
的独立证据检索工具。

## 1. 冻结结论

当前可以进入第二次冻结收口，但严格意义上的冻结仍需要一个干净 Git 提交作为
不可变边界。当前工作树已经完成 DS-06，阶段结论为 `PASS WITH NOTES`，增强检索
候选结论为 `NO_GO`。这表示当前 BM25、Hybrid、Reranker 配置不应上线，不表示
Dense `/retrieve` 基线不可用。

## 2. 固定范围

- DocuMind v2.2.0 的单文档纯检索基线；公共 Schema `1.0`、`dense-v1` 和现有
  阈值行为保持不变。
- DS-03 三来源确定性规范化及结构/哈希验证。
- DS-04 75 份合成代表性文档、235 个生产 Chunk、400 题探索池、100 题人工确认
  gold（94 approve、6 modify、0 delete）。
- DS-05 validation/holdout 各 50 题的泄漏审计和冻结指纹。
- DS-06 Dense、BM25、Hybrid、Reranker Top-5/Top-8 对照、一次性 holdout 和严格
  `NO_GO` 决策。
- ScholarTrace 兼容边界：DocuMind `2.2.0 纯检索交付基线`、`/api/v1/retrieve`
  Schema `1.0`、一个 `document_key`、一个 `expected_index_id`、Dense-only。

## 3. 提交候选边界

应纳入同一个 P2 evidence checkpoint 的内容：

- `evaluation/representative_dataset.py`
- `evaluation/representative_split_audit.py`
- `evaluation/ds06_runner.py`
- `evaluation/representative_data/`
- `evaluation/datasets/p2_retrieval_v2/`
- DS-04、DS-05、DS-06 的 JSON/Markdown 报告
- 对应的 `tests/` 专项测试
- `README.md`、`docs/EVALUATION.md`、`docs/PROJECT_STRUCTURE.md`、P2 计划和本文档

明确排除：

- `agent/` 私有过程记录
- `data/evaluation_sources/` raw 数据和 `.part` 文件
- Ollama、Milvus、SQLite、上传目录和模型缓存
- `.pytest_cache`、临时 pycache、日志和其他本地生成物

## 4. 已完成验证

| 检查 | 结果 |
|---|---|
| DS-06 专项与 DS-05 定向测试 | `9 passed` |
| 全量 Python 测试 | `315 passed, 1 skipped, 178 subtests passed` |
| Black | 通过 |
| compileall | 通过 |
| `git diff --check` | 通过 |
| DS-05 freeze validate | 通过 |
| Holdout 执行次数 | 1 次 |
| 公共 API 变更 | 0 |

DS-06 报告 SHA-256：

- validation：`363272c21d1fa33430122bb4a35dec1d9d6d9b2bb1a49e377efece14a8a1bbf3`
- holdout：`8a80ab258e6752ed4c0ab6962eeb9f3dd29a3ecfa675cead190a1e0031a28d7a`
- decision：`60d97ea874cc4dcd58b37f705b6727ba1311a4e18fcf23d24a933170e8b3f462`

报告是在最终提交前的工作树上生成的。提交时不得修改评测输入、代码路径或报告
字节；提交后应复核文件哈希和 `git show` 内容。由于 holdout 只允许执行一次，不能
为了得到“干净提交报告”而重复运行同一 holdout。

## 5. ScholarTrace 使用条件

第二次冻结后可以继续用于 ScholarTrace 的本地/可信私网 M2/MVP：

1. 部署已验证的 DocuMind `2.2.0 纯检索交付基线`，不要使用含未审查实验改动的脏工作树。
2. 检查 `/api/v1/health/ready`，确认 `components.retrieval=ready`。
3. 先预热 `qwen3-embedding`，完成全部论文的检索，再启动本地 `qwen3:8b` 生成。
4. 每次请求绑定唯一 `document_key` 和 `expected_index_id`，保存 Chunk、index 和
   source hash。

该冻结不承诺公网认证、多租户、跨文档批量检索、异步摄取、高可用、全量数据吞吐或
线上 Reranker。
