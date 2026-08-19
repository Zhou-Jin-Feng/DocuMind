# v2.0.5 评测数据集

本目录只包含仓库内人工编写的合成材料，不使用私人文档、生产数据或真实凭据。

- `dataset.jsonl`：28 条答案质量 `holdout`，供固定真实 Generator/Judge 的旧 Prompt 对照和后续加固对照使用。
- `threshold_dataset.jsonl`：validation 5 正/15 负、holdout 5 正/10 负，供后续 L2 distance 阈值校准使用。
- `documents/`：两个数据集共用的 11 份 TXT 语料；三份 `injection-*` 文档包含故意放置的不可信指令。

两个 JSONL 的用途不可互换。答案集中的 6 条无答案和 3 条信息不足案例用于端到端拒答评测，不能代替阈值集；阈值集的 holdout 不得用于选择候选阈值。数据或语料变更后必须同步更新规范化指纹、审计测试和评测文档，旧报告会因指纹不兼容而失效。

当前规范化 SHA-256：

```text
dataset.jsonl           f5eb00ddc448772e6369f8e2b8ae798cecf4736e2f7dc6619df49a728108055d
threshold_dataset.jsonl 8853bf2aba5bc1266bd7202b6f7feb084a0fca242d475d6c2204928fdab12210
documents/              7655501aca56852fd4db7755b8fea6512705b837cd070d5e9e00ad373a878103
```
