# P2 Retrieval Data Sources

This directory contains commit-safe source metadata and DS-03 normalized data
contracts. Raw and normalized text remains local under
`data/evaluation_sources/` and is ignored by Git.

## Normalized Snapshot V1

Each source produces three canonical UTF-8 JSONL files:

- `documents.jsonl`: namespaced stable ID, official source identity, immutable
  revision, language, authority state and content SHA-256;
- `queries.jsonl`: namespaced stable ID, official query identity, text,
  official split, answerability and primary category;
- `qrels.jsonl`: namespaced query/document identities, integer `0-3` relevance
  and official label provenance.

The root `snapshot.json` binds the pinned source manifest, conversion policy,
counts and per-file/per-source/aggregate fingerprints. Records use sorted-key,
compact JSON and LF line endings. Stable IDs use a SHA-256 digest over the
source snapshot namespace, entity type and unmodified official entity ID.

The checked-in contracts are:

- `contracts/documents-v1.schema.json`;
- `contracts/queries-v1.schema.json`;
- `contracts/qrels-v1.schema.json`;
- `contracts/snapshot-v1.schema.json`.

## Build And Validate

Use the project development environment because Parquet conversion requires
`pyarrow` and output validation requires `jsonschema`:

```powershell
.\venv\Scripts\python.exe -m evaluation.data_source_normalization build `
  --report-json evaluation/reports/p2_ds03_normalization_evidence_v1.json `
  --report-markdown evaluation/reports/p2_ds03_normalization_evidence_v1.md

.\venv\Scripts\python.exe -m evaluation.data_source_normalization validate
```

An existing non-empty normalized root is never overwritten unless `--replace`
is explicit. Publication uses a sibling staging directory and keeps the prior
root recoverable until the replacement succeeds.

The adapters preserve upstream text apart from BOM and line-ending
canonicalization. They do not repair source encoding defects, synthesize
labels, embed text, write Milvus, call a model or alter the public retrieve API.

## 数据治理约束

- 获取源数据前记录来源、固定版本及再分发条件；可下载不等于允许将原文随仓库发布。
- 原始私人资料和运行数据不进入 Git；派生样本经敏感信息检查后才纳入公开数据。
- 保留来源 ID 和官方 split；Gold 来自官方标注或人工审核，不由模型自评替代。
- 清理仅作用于清单管理的精确数据路径，不使用覆盖整个工作目录的删除规则。
