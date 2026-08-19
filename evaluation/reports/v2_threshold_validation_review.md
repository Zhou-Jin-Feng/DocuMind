# v2.0.7 Dense L2 检索阈值校准复核

复核日期：2026-08-19

结论：validation 没有产生满足预设约束的候选阈值，因此不启用参考部署阈值，代码默认值继续保持 `None`，并按协议不运行 holdout。

## 实验边界

| 项目 | 固定值 |
|---|---|
| 父提交 | `83a46ac` |
| 数据集 | `evaluation/datasets/v2_answer_quality/threshold_dataset.jsonl` |
| validation | 5 条正样本、15 条困难负样本 |
| holdout | 5 条正样本、10 条困难负样本；本次未运行 |
| 语料 | `evaluation/datasets/v2_answer_quality/documents`，11 份合成 TXT |
| Embedding | Ollama `qwen3-embedding`，实际维度 4096 |
| 检索 | Dense，Milvus L2，Top-K=3，无阈值原始运行 |
| 分块 | size 500，overlap 100，共 11 个 Chunk |
| 数据集 SHA-256 | `8853bf2aba5bc1266bd7202b6f7feb084a0fca242d475d6c2204928fdab12210` |
| 语料 SHA-256 | `7655501aca56852fd4db7755b8fea6512705b837cd070d5e9e00ad373a878103` |
| 选择策略 | `largest-passing-adjacent-midpoint-v1` |

正式运行发生在任务七实现工作区，因此代码尚未提交。原始报告只读取冻结数据集和语料，并使用新增的 split 隔离、L2 元数据与既有真实 Retriever；该状态不会被描述为干净提交上的发布基线。

## 预设约束

候选只取 validation 实际观测 distance 的相邻中点，不扫描任意硬编码区间。候选必须同时满足：

- answerable Recall@3 相对无阈值基线下降不超过 `0.02`；
- no-answer retrieval accuracy 不低于 `0.90`；
- successful case rate 等于 `1.00`。

若有多个候选通过，固定选择数值最大的候选，以保留最宽的正常召回边界。validation 没有候选时，不查看 holdout，也不降低约束。

## 结果复核

无阈值原始运行 20/20 成功。5 条正样本的 Recall@3 和 MRR@3 都是 `1.0000`；15 条困难负样本都返回了 3 个结果，无答案检索准确率为 `0.0000`。

扫描了 59 个相邻中点候选，关键边界如下：

| 候选阈值 | Recall@3 | No-answer accuracy | 错误拒答率 | 结论 |
|---:|---:|---:|---:|---|
| `0.717509448528` | 0.4000 | 0.9333 | 0.6000 | 无答案约束通过，但严重损失正常召回 |
| `0.752467751503` | 0.6000 | 0.9333 | 0.4000 | 无答案约束通过，但严重损失正常召回 |
| `0.900638788939` | 1.0000 | 0.4667 | 0.0000 | 保持召回，但无答案约束失败 |

全部候选的 successful case rate 都是 `1.0000`。正负样本 Top-1 distance 区间重叠：正样本为 `0.6420` 至 `0.8903`，困难负样本为 `0.7050` 至 `1.0464`。单一全局 L2 阈值无法在这份语料上同时达到正常召回与无答案过滤目标。

## 启用决策

- `selected_threshold=null`；
- `holdout_status=not_run_no_validation_candidate`；
- `enable_reference_threshold=false`；
- `Settings.retrieval_score_threshold` 保持 `None`；
- `.env.example` 不写入推荐阈值；
- Web、SSE、无上下文响应、Metrics 和日志行为均不改变。

这不是阈值功能失效。系统仍支持显式配置最大 L2 distance，但当前实验不支持把某个数值描述为 `qwen3-embedding` 或任意用户语料的可靠默认值。后续 Prompt 加固不得把本次失败改写成“参考部署已启用检索拒答”。

## 工件校验

| 工件 | SHA-256 |
|---|---|
| `v2_threshold_validation_raw.json` | `4451fe92be78bb9d213e3e7b2435f4a308fa8675050f0691e03bbd7931e80de0` |
| `v2_threshold_validation_raw.md` | `62a0b0f1d90cd55189d280d3e7568c912d9e136f62082ed1e28a1f23cf49c463` |
| `v2_threshold_validation_scan.json` | `4f13a67527eb9efc114e40738c061dc643bf7b208162cc139ec6648b44b730e5` |
| `v2_threshold_validation_scan.md` | `bb4c5b3c8c44da4a432c9499efe9930431fcc1e215a94020fbbb57ea4415cc74` |
