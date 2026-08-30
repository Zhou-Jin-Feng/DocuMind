# DocuMind 2.2.0 交付范围与验证

状态：`FROZEN / PASS WITH NOTES`

本文记录已验证的交付范围，不是公网多租户生产认证。系统为
可运行、可复现、工程可信的本地单用户或可信私网 RAG 服务，并作为 ScholarTrace
的独立证据检索工具。

## 1. 冻结结论

本次收口将第二次冻结固定在一个干净 Git 提交上。DS-06 阶段结论为
`PASS WITH NOTES`，增强检索候选结论为 `NO_GO`；这表示当前 BM25、Hybrid、
Reranker 配置不应上线，不表示 Dense `/retrieve` 基线不可用。

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

## 3. ScholarTrace M2 跨项目验收

ScholarTrace 已在已验证的 DocuMind `2.2.0 纯检索交付基线` 上完成真实在线
`upload -> status -> retrieve` 验收，不是仅有接口兼容测试。验收使用 3 篇版本化
公开 arXiv PDF，DocuMind readiness 返回 HTTP 200 且 `retrieval=ready`；3 次检索
全部一次成功，返回 15 个 Chunk，并生成 11 条全文 Evidence。

ScholarTrace Consumer 对每个返回 Chunk 执行论文身份、`document_key`、active
`index_id`、源文件 SHA-256、Chunk hash、连续 rank、页码、Chunk 定位和引用位置的
fail-closed 校验，最终 Evidence 可回链到确定的论文全文位置。正式报告
`docs/M2_EVIDENCE_BASELINE.md` 与机器报告 `evaluation/reports/m2_live_documind_smoke.json`
的阶段结论均为 `PASS`。

该证据只证明当前本地/可信私网 M2 集成和契约可靠性，不外推为大规模吞吐、语义
蕴含质量或公网生产能力。

## 5. 已完成验证

| 检查 | 结果 |
|---|---|
| DS-06 专项与 DS-05 定向测试 | `9 passed` |
| 全量 Python 测试 | `316 passed, 1 skipped, 178 subtests passed` |
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

## 6. ScholarTrace 使用条件

第二次冻结后可以继续用于 ScholarTrace 的本地/可信私网 M2/MVP：

1. 部署已验证的 DocuMind `2.2.0 纯检索交付基线`，不要使用含未审查实验改动的脏工作树。
2. 检查 `/api/v1/health/ready`，确认 `components.retrieval=ready`。
3. 先预热 `qwen3-embedding`，完成全部论文的检索，再启动本地 `qwen3:8b` 生成。
4. 每次请求绑定唯一 `document_key` 和 `expected_index_id`，保存 Chunk、index 和
   source hash。

该冻结不承诺公网认证、多租户、跨文档批量检索、异步摄取、高可用、全量数据吞吐或
线上 Reranker。
