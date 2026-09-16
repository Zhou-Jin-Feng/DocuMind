# 历史交付证据：2.2.0 纯检索基线

本页记录 2026 年 8 月的交付与实验快照，不代表任意当前工作树已经完成新的真实部署或发布验收。当前运行方式见 [README](../README.md)，接口语义见 [RETRIEVE_API](RETRIEVE_API.md)。

## 范围

- 单文档 Dense 纯检索，Schema `1.0`、`dense-v1`；要求匹配的 active index。
- 数据来源规范化、合成代表性语料、人工 Gold 审核和 validation/holdout 隔离。
- 检索执行资源控制、独立 readiness 与观测。
- ScholarTrace 对应基线的上传/状态/纯检索联调及 Evidence 校验。

不包含公网认证、多租户授权、跨文档批量、线上 Reranker、完整高可用或大规模吞吐保证。

## DS-06 检索证据

| 项目 | 历史记录 |
|---|---|
| 语料 | 75 份合成代表性文档，235 个按生产分块器生成的 Chunk |
| 探索与审核 | 400 题探索池；100 题正式 Gold（94 approve、6 modify） |
| 数据划分 | validation / holdout 各 50 题 |
| 候选 | Dense、BM25、Hybrid、CPU Reranker；Reranker深度仅在validation选择 |
| 决策 | 增强候选 `NO_GO`，保留 Dense 基线 |
| 解释边界 | Reranker有质量提升但延迟超门禁；结果只适用于对应数据和配置 |

原始证据：

- [Validation 报告](../evaluation/reports/p2_ds06_validation_v1.json)
- [Holdout 报告](../evaluation/reports/p2_ds06_holdout_v1.json)
- [候选决策 JSON](../evaluation/reports/p2_ds06_final_decision_v1.json)
- [候选决策说明](../evaluation/reports/p2_ds06_final_decision_v1.md)

输入指纹、配置、指标分母和错误记录以这些文件及对应评测协议为准。历史 holdout 只执行一次；不能为了更新版本标识而重复运行同一 holdout 或改写原始结果。

## ScholarTrace 对应基线联调

历史联调使用三篇版本化公开 arXiv 论文：上传、状态检查与纯检索成功，返回15个Chunk，形成11条全文Evidence。Consumer核对论文身份、document_key、active index、源文件/Chunk哈希、排序与定位。

证据位于 ScholarTrace 仓库的 `docs/M2_EVIDENCE_BASELINE.md` 和 `evaluation/reports/m2_live_documind_smoke.json`。该记录证明限定的本地/可信私网契约兼容，不外推为通用语义蕴含质量、并发能力或当前版本的新验收。

## 当时的自动检查快照

| 检查 | 历史结果 |
|---|---|
| DS-06专项及DS-05定向测试 | 9 passed |
| 后端全量 | 316 passed、1 skipped、178 subtests passed |
| 格式、编译、Git差异及split校验 | 通过 |
| 公共检索Schema变化 | 无 |

这些数量属于当时的测试集合，不是当前测试数量。原始报告曾在提交前的工作树生成；保留其代码/输入身份，不将后续文件整理包装成新的实验结果。

## 当前接入应重新确认的条件

- 目标服务和所需模型可用，`components.retrieval=ready`。
- 请求中保持单文档和预期索引约束，不绕过失效索引检查。
- 部署版本与Consumer契约一致，先在独立测试数据上验证调用链。
- 有界Embedding驻留和冷加载窗口只是资源配置，不能作为GPU容量或永久可用保证。

接口迁移与回退的版本差异见 [ScholarTrace接入](SCHOLARTRACE_INTEGRATION.md)，数据方法与结果解释见 [评测说明](EVALUATION.md)。
