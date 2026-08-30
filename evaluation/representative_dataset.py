"""Build and validate the DS-04 DocuMind representative retrieval dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from langchain_core.documents import Document

from app.core.document_chunker import DocumentChunker
from evaluation.data_source_normalization import canonical_json_bytes, canonical_sha256
from evaluation.data_source_downloader import sha256_file

DESIGN_SCHEMA_VERSION = "p2-representative-design-v1"
DOCUMENT_SCHEMA_VERSION = "p2-representative-document-v1"
CHUNK_SCHEMA_VERSION = "p2-representative-chunk-v1"
EXPLORATION_SCHEMA_VERSION = "p2-representative-exploration-v1"
GOLD_CANDIDATE_SCHEMA_VERSION = "p2-representative-gold-candidate-v1"
REVIEW_DECISION_SCHEMA_VERSION = "p2-representative-review-decision-v1"
GOLD_DATASET_SCHEMA_VERSION = "p2-representative-gold-v1"
SNAPSHOT_SCHEMA_VERSION = "p2-representative-snapshot-v1"
EVIDENCE_SCHEMA_VERSION = "p2-ds04-pre-review-evidence-v1"
FINAL_EVIDENCE_SCHEMA_VERSION = "p2-ds04-final-review-evidence-v1"
FINAL_SNAPSHOT_STATUS = "gold_confirmed"
DEFAULT_DESIGN = Path("evaluation/representative_data/design.json")
DEFAULT_CONTRACT_ROOT = Path("evaluation/representative_data/contracts")
DEFAULT_OUTPUT_ROOT = Path("evaluation/datasets/p2_retrieval_v2")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
EXPECTED_TOPICS = 25
EXPECTED_DOCUMENTS = 75
EXPECTED_EXPLORATION = 400
EXPECTED_GOLD_CANDIDATES = 100
STATE_ORDER = ("active", "draft", "superseded")
CATEGORIES = (
    "exact_lexical",
    "semantic",
    "difficult_negative",
    "authority_version",
    "non_plain_text",
    "general_operations",
)
FORMAT_SHAPES = (
    "table_extract",
    "yaml_config",
    "json_log",
    "ocr_extract",
    "mixed_zh_en",
)
_TOPIC_FIELDS = {
    "id",
    "domain",
    "title",
    "semantic_prompt",
    "unknown_identifier",
    "format_shape",
    "active",
    "draft",
    "superseded",
}
_STATE_FIELDS = {"control_id", "version", "value", "rule", "procedure"}
_QUESTION_SCHEMA_FILES = {
    "documents": "documents-v1.schema.json",
    "chunks": "chunks-v1.schema.json",
    "exploration": "exploration-v1.schema.json",
    "gold_candidates": "gold-candidates-v1.schema.json",
    "review_decisions": "review-decisions-v1.schema.json",
    "gold_dataset": "gold-dataset-v1.schema.json",
    "snapshot": "snapshot-v1.schema.json",
}
_CREDENTIAL_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|password|token)\s*[:=]\s*[^\s<]{12,}"),
)
_PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class RepresentativeDatasetError(RuntimeError):
    """The representative dataset violates a DS-04 contract or quota."""


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RepresentativeDatasetError(f"{field_name} must be a non-empty string")
    return value.strip()


def _exact_fields(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if not isinstance(value, Mapping):
        raise RepresentativeDatasetError(f"{name} must be an object")
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        raise RepresentativeDatasetError(
            f"{name} fields differ: missing={missing}, unknown={unknown}"
        )


def _stable_id(entity_type: str, source_id: str) -> str:
    digest = canonical_sha256(
        {
            "dataset": "p2-retrieval-v2",
            "entity_type": entity_type,
            "source_id": source_id,
        }
    )
    return f"p2rep:{entity_type}:{digest}"


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    with path.open("wb") as handle:
        for record in records:
            payload = canonical_json_bytes(record) + b"\n"
            handle.write(payload)
            digest.update(payload)
            count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RepresentativeDatasetError(
                    f"invalid JSONL at {path}:{line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise RepresentativeDatasetError(
                    f"JSONL record must be an object at {path}:{line_number}"
                )
            records.append(record)
    return records


def load_design(path: Path = DEFAULT_DESIGN) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _exact_fields(payload, {"schema_version", "dataset_id", "topics"}, "design")
    if payload["schema_version"] != DESIGN_SCHEMA_VERSION:
        raise RepresentativeDatasetError("unsupported representative design schema")
    if payload["dataset_id"] != "p2-retrieval-v2":
        raise RepresentativeDatasetError("unexpected representative dataset ID")
    topics = payload["topics"]
    if not isinstance(topics, list) or len(topics) != EXPECTED_TOPICS:
        raise RepresentativeDatasetError(
            f"design requires exactly {EXPECTED_TOPICS} topics"
        )
    topic_ids: set[str] = set()
    control_ids: set[str] = set()
    unknown_identifiers: set[str] = set()
    for position, topic in enumerate(topics):
        _exact_fields(topic, _TOPIC_FIELDS, f"topic[{position}]")
        topic_id = _text(topic["id"], "topic.id")
        if not re.fullmatch(r"T\d{2}", topic_id):
            raise RepresentativeDatasetError(f"invalid topic ID: {topic_id}")
        if topic_id in topic_ids:
            raise RepresentativeDatasetError(f"duplicate topic ID: {topic_id}")
        topic_ids.add(topic_id)
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", topic["domain"]):
            raise RepresentativeDatasetError(
                f"invalid filename-safe topic domain: {topic['domain']}"
            )
        if topic["format_shape"] not in FORMAT_SHAPES:
            raise RepresentativeDatasetError(
                f"unsupported format shape: {topic['format_shape']}"
            )
        for field_name in ("domain", "title", "semantic_prompt", "unknown_identifier"):
            _text(topic[field_name], f"{topic_id}.{field_name}")
        unknown_identifier = topic["unknown_identifier"]
        if not re.fullmatch(r"DM-[A-Z0-9-]+-UNKNOWN", unknown_identifier):
            raise RepresentativeDatasetError(
                f"invalid unknown identifier: {unknown_identifier}"
            )
        if unknown_identifier in unknown_identifiers:
            raise RepresentativeDatasetError(
                f"duplicate unknown identifier: {unknown_identifier}"
            )
        unknown_identifiers.add(unknown_identifier)
        for state_name in STATE_ORDER:
            state = topic[state_name]
            _exact_fields(state, _STATE_FIELDS, f"{topic_id}.{state_name}")
            for field_name in _STATE_FIELDS:
                _text(state[field_name], f"{topic_id}.{state_name}.{field_name}")
            control_id = state["control_id"]
            if not re.fullmatch(r"DM-[A-Z0-9-]+-(?:ACT|DRF|OLD)", control_id):
                raise RepresentativeDatasetError(
                    f"invalid representative control ID: {control_id}"
                )
            if control_id in control_ids:
                raise RepresentativeDatasetError(
                    f"duplicate representative control ID: {control_id}"
                )
            control_ids.add(control_id)
    expected_topic_ids = {f"T{number:02d}" for number in range(1, 26)}
    if topic_ids != expected_topic_ids:
        raise RepresentativeDatasetError(
            "representative topic IDs must be the contiguous range T01-T25"
        )
    return payload


def _state_label(state_name: str) -> str:
    return {
        "active": "当前生效",
        "draft": "草案未生效",
        "superseded": "历史已废止",
    }[state_name]


def _structured_extract(topic: Mapping[str, Any], state: Mapping[str, Any]) -> str:
    control_id = state["control_id"]
    marker = f"{control_id}-DATA"
    shape = topic["format_shape"]
    if shape == "table_extract":
        return (
            f"Table-Control: {marker}\n"
            "| Field | Value | Review |\n|---|---|---|\n"
            f"| control_id | {control_id} | pinned |\n"
            f"| version | {state['version']} | explicit |\n"
            f"| configured_value | {state['value']} | {_state_label(_state_for(topic, state))} |"
        )
    if shape == "yaml_config":
        return (
            f"Config-Control: {marker}\n```yaml\n"
            f"control_id: {control_id}\nversion: {state['version']}\n"
            f"configured_value: {json.dumps(state['value'], ensure_ascii=False)}\n"
            f"authority: {_state_label(_state_for(topic, state))}\n```"
        )
    if shape == "json_log":
        payload = {
            "authority": _state_label(_state_for(topic, state)),
            "control_id": control_id,
            "configured_value": state["value"],
            "event": marker,
            "version": state["version"],
        }
        return (
            "Event-Control: "
            + marker
            + "\n```json\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n```"
        )
    if shape == "ocr_extract":
        return (
            f"OCR-Control: {marker}\n"
            "[OCR EXTRACT / page 2]\n"
            f"C0NTR0L  ID : {control_id}\n"
            f"VERSI0N : {state['version']}\n"
            f"VALUE : {state['value']}\n"
            "注：字符 0/O 的混淆只来自扫描版式，控制项身份以上方标准文本为准。"
        )
    return (
        f"Bilingual-Control: {marker}\n"
        f"Control ID / 控制项: {control_id}\n"
        f"Effective version / 版本: {state['version']}\n"
        f"Configured value / 配置值: {state['value']}\n"
        f"Authority / 权威状态: {_state_label(_state_for(topic, state))}"
    )


def _state_for(topic: Mapping[str, Any], state: Mapping[str, Any]) -> str:
    for name in STATE_ORDER:
        if topic[name] is state:
            return name
    raise RepresentativeDatasetError("state does not belong to topic")


def _render_document(topic: Mapping[str, Any], state_name: str) -> str:
    state = topic[state_name]
    label = _state_label(state_name)
    active = topic["active"]
    authority_note = {
        "active": (
            "本文件是本主题当前生效的控制依据。草案和历史文件即使关键词更相似，"
            "也不能覆盖本文件；执行与回答必须优先引用当前控制项。"
        ),
        "draft": (
            f"本文件只记录评审中的建议，尚未替代 {active['control_id']}。任何线上操作"
            "仍必须遵守当前生效文件，草案值只能用于离线讨论。"
        ),
        "superseded": (
            f"本文件仅用于解释历史行为，已由 {active['control_id']} 取代。当前故障处理"
            "不得照搬旧值；需要比较版本时应同时引用现行控制项。"
        ),
    }[state_name]
    return f"""{topic['title']} - {label}

文档编号: DM-{topic['id']}-{state_name.upper()}
主题域: {topic['domain']}
authority_state: {state_name}
document_version: {state['version']}

## 适用范围

本文描述 DocuMind 在“{topic['title']}”主题下的一个完整版本状态。文档将规则、执行步骤、结构化摘录、失败边界和审计要求放在同一主题内，供上传、分块和检索评测使用。{authority_note}

## 核心规则

Control ID: {state['control_id']} | Rule: {state['rule']}

该版本冻结值为“{state['value']}”。检索结果必须同时保留控制项、文档版本和权威状态，不能只凭关键词相似度把草案或废止版本当作当前答案。

## 执行步骤

Procedure-Control: {state['control_id']}-PROC | Procedure: {state['procedure']}

执行人员应先确认版本与状态，再核对输入条件，最后记录可追溯结果。若前置条件不满足，应停止在安全状态并返回明确错误；不得通过扩大重试、删除数据或跳过完整性检查来掩盖失败。

## 结构化或非纯文本摘录

{_structured_extract(topic, state)}

## 冲突与失败边界

同主题文件可能包含相似术语但不同版本值。发生冲突时，当前生效文件的直接证据等级最高；草案可以作为背景，历史文件只用于解释旧行为。对文档没有写明的人员、未来版本、外部账号或秘密值必须判定为不可回答，不能根据常识补齐。

## 审计与回滚

每次执行至少记录 Control ID、document_version、authority_state 和结果摘要。回滚只能回到已验证的稳定状态，不能把 draft 当作回滚目标。本文为项目生成的合成评测材料，不包含真实客户、员工、邮箱、手机号、访问令牌、生产路径或业务文档。
"""


def _document_filename(topic: Mapping[str, Any], state_name: str) -> str:
    return f"{topic['id'].lower()}-{topic['domain']}-{state_name}.txt"


def _find_chunk(
    chunk_records: Sequence[Mapping[str, Any]], document_id: str, control_id: str
) -> Mapping[str, Any]:
    matches = [
        record
        for record in chunk_records
        if record["document_id"] == document_id
        and control_id in record["content_preview_source"]
    ]
    if not matches:
        raise RepresentativeDatasetError(
            f"no generated chunk contains evidence control {control_id}"
        )
    return matches[0]


def _build_documents(
    topics: Sequence[Mapping[str, Any]], staging: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[tuple[str, str], str]]:
    chunker = DocumentChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    document_records: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    document_ids: dict[tuple[str, str], str] = {}
    documents_root = staging / "documents"
    documents_root.mkdir(parents=True)
    for topic in topics:
        for state_name in STATE_ORDER:
            state = topic[state_name]
            filename = _document_filename(topic, state_name)
            content = _render_document(topic, state_name)
            path = documents_root / filename
            path.write_text(content, encoding="utf-8", newline="\n")
            document_id = _stable_id("document", f"{topic['id']}:{state_name}")
            document_ids[(topic["id"], state_name)] = document_id
            chunks = chunker.chunk_documents_recursive(
                [
                    Document(
                        page_content=content,
                        metadata={
                            "document_id": document_id,
                            "source_file": filename,
                        },
                    )
                ]
            )
            for chunk in chunks:
                chunk_records.append(
                    {
                        "schema_version": CHUNK_SCHEMA_VERSION,
                        "id": chunk.metadata["chunk_id"],
                        "document_id": document_id,
                        "chunk_index": chunk.metadata["chunk_index"],
                        "char_count": len(chunk.page_content),
                        "content_sha256": hashlib.sha256(
                            chunk.page_content.encode("utf-8")
                        ).hexdigest(),
                        "content_preview_source": chunk.page_content,
                    }
                )
            document_records.append(
                {
                    "schema_version": DOCUMENT_SCHEMA_VERSION,
                    "id": document_id,
                    "topic_id": topic["id"],
                    "domain": topic["domain"],
                    "title": f"{topic['title']} - {_state_label(state_name)}",
                    "filename": filename,
                    "language": "zh-CN-mixed-en",
                    "source_format": topic["format_shape"],
                    "authority_state": state_name,
                    "document_version": state["version"],
                    "content_sha256": hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest(),
                    "chunk_count": len(chunks),
                    "control_ids": [
                        state["control_id"],
                        f"{state['control_id']}-PROC",
                        f"{state['control_id']}-DATA",
                    ],
                    "privacy_state": "synthetic_safe_pending_human",
                    "review_status": "pending_human",
                }
            )
    return document_records, chunk_records, document_ids


def _qrel(
    topic: Mapping[str, Any],
    state_name: str,
    marker_suffix: str,
    grade: int,
    document_ids: Mapping[tuple[str, str], str],
    chunk_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    state = topic[state_name]
    control_id = state["control_id"] + marker_suffix
    document_id = document_ids[(topic["id"], state_name)]
    chunk = _find_chunk(chunk_records, document_id, control_id)
    evidence_quote = {
        "": state["rule"],
        "-PROC": state["procedure"],
        "-DATA": state["value"],
    }.get(marker_suffix)
    if evidence_quote is None:
        raise RepresentativeDatasetError(
            f"unsupported evidence marker suffix: {marker_suffix}"
        )
    if evidence_quote not in chunk["content_preview_source"]:
        raise RepresentativeDatasetError(
            f"evidence quote is absent from referenced chunk: {control_id}"
        )
    return {
        "document_id": document_id,
        "chunk_id": chunk["id"],
        "relevance_grade": grade,
        "evidence_control_id": control_id,
        "evidence_quote": evidence_quote,
        "rationale": f"{_state_label(state_name)}文档中的直接控制证据",
    }


def _question(
    topic: Mapping[str, Any],
    slot: int,
    question: str,
    category: str,
    qrels: Sequence[Mapping[str, Any]],
    ambiguity_state: str,
) -> dict[str, Any]:
    answerable = bool(qrels)
    return {
        "schema_version": EXPLORATION_SCHEMA_VERSION,
        "id": f"REP-{topic['id']}-{slot:02d}",
        "question": question,
        "answerable": answerable,
        "primary_category": category,
        "secondary_categories": [
            value
            for value in (
                "no_answer" if not answerable else None,
                (
                    "authority_sensitive"
                    if category in {"difficult_negative", "authority_version"}
                    else None
                ),
            )
            if value is not None
        ],
        "topic_id": topic["id"],
        "fact_family_id": f"{topic['id'].casefold()}-fact-{slot:02d}",
        "candidate_qrels": list(qrels),
        "label_provenance": "assisted_unverified",
        "ambiguity_state": ambiguity_state,
        "privacy_state": "synthetic_safe_pending_human",
        "review_status": "pending_human",
    }


def _build_questions(
    topics: Sequence[Mapping[str, Any]],
    document_ids: Mapping[tuple[str, str], str],
    chunk_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for topic in topics:
        active = topic["active"]
        draft = topic["draft"]
        old = topic["superseded"]

        def rel(state: str, suffix: str = "", grade: int = 3) -> dict[str, Any]:
            return _qrel(topic, state, suffix, grade, document_ids, chunk_records)

        records.extend(
            [
                _question(
                    topic,
                    1,
                    f"控制项 {active['control_id']} 的当前冻结值和规则是什么？",
                    "exact_lexical",
                    [rel("active")],
                    "clear",
                ),
                _question(
                    topic,
                    2,
                    f"{topic['semantic_prompt']}，现行规范要求怎样处理？",
                    "semantic",
                    [rel("active", "-PROC")],
                    "clear",
                ),
                _question(
                    topic,
                    3,
                    f"{draft['control_id']} 与 {active['control_id']} 的值冲突时，线上应采用哪一个，为什么？",
                    "difficult_negative",
                    [rel("active", grade=3), rel("draft", grade=1)],
                    "multiple_relevant_authority_ordered",
                ),
                _question(
                    topic,
                    4,
                    f"在 {topic['format_shape']} 摘录中，{active['control_id']} 对应的配置值是什么？",
                    "non_plain_text",
                    [rel("active", "-DATA")],
                    "clear",
                ),
                _question(
                    topic,
                    5,
                    f"“{topic['title']}”同时检索到 active、draft、superseded 三份文件时，哪份可以作为当前直接证据？",
                    "authority_version",
                    [
                        rel("active", grade=3),
                        rel("draft", grade=1),
                        rel("superseded", grade=1),
                    ],
                    "multiple_relevant_authority_ordered",
                ),
                _question(
                    topic,
                    6,
                    f"执行“{topic['title']}”当前流程时，前置核对和安全停止步骤是什么？",
                    "general_operations",
                    [rel("active", "-PROC")],
                    "clear",
                ),
                _question(
                    topic,
                    7,
                    f"未生效控制项 {draft['control_id']} 提议的值是什么？",
                    "exact_lexical",
                    [rel("draft"), rel("active", grade=1)],
                    "clear_but_non_authoritative",
                ),
                _question(
                    topic,
                    8,
                    f"如果只讨论“{topic['title']}”的下一版建议，草案准备怎样执行？",
                    "semantic",
                    [rel("draft", "-PROC")],
                    "clear_but_non_authoritative",
                ),
                _question(
                    topic,
                    9,
                    f"历史控制项 {old['control_id']} 与当前行为有什么区别，故障处理中能否继续使用旧值？",
                    "difficult_negative",
                    [rel("active", grade=3), rel("superseded", grade=2)],
                    "multiple_relevant_authority_ordered",
                ),
                _question(
                    topic,
                    10,
                    f"从草案的 {topic['format_shape']} 摘录读取，{draft['control_id']} 配置了什么？",
                    "non_plain_text",
                    [rel("draft", "-DATA")],
                    "clear_but_non_authoritative",
                ),
                _question(
                    topic,
                    11,
                    f"{old['control_id']} 记录的是哪个历史版本，当前为什么不能把它当作权威规则？",
                    "authority_version",
                    [rel("superseded"), rel("active", grade=2)],
                    "multiple_relevant_authority_ordered",
                ),
                _question(
                    topic,
                    12,
                    f"在复盘旧系统时，“{topic['title']}”以前采用什么步骤？",
                    "general_operations",
                    [rel("superseded", "-PROC")],
                    "clear_historical_only",
                ),
                _question(
                    topic,
                    13,
                    f"未收录控制项 {topic['unknown_identifier']} 的生产值是多少？",
                    "exact_lexical",
                    [],
                    "unanswerable_absent",
                ),
                _question(
                    topic,
                    14,
                    f"明年尚未发布的“{topic['title']}”最终政策会如何调整？",
                    "semantic",
                    [],
                    "unanswerable_future",
                ),
                _question(
                    topic,
                    15,
                    f"在三份文件都没有记录外部托管平台的情况下，该平台对“{topic['title']}”的强制值是什么？",
                    "difficult_negative",
                    [],
                    "unanswerable_external",
                ),
                _question(
                    topic,
                    16,
                    f"负责“{topic['title']}”审批的真实员工姓名、手机号和邮箱是什么？",
                    "general_operations",
                    [],
                    "unanswerable_private",
                ),
            ]
        )
    return records


def _select_gold_candidates(
    questions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    split_topics = {
        "validation": {f"T{number:02d}" for number in range(1, 13)},
        "holdout": {f"T{number:02d}" for number in range(13, 26)},
    }
    category_targets = {
        "validation": {
            "exact_lexical": 8,
            "semantic": 7,
            "difficult_negative": 10,
            "authority_version": 5,
            "non_plain_text": 5,
            "general_operations": 15,
        },
        "holdout": {
            "exact_lexical": 7,
            "semantic": 8,
            "difficult_negative": 10,
            "authority_version": 5,
            "non_plain_text": 5,
            "general_operations": 15,
        },
    }
    no_answer_targets = {
        "exact_lexical": 3,
        "semantic": 3,
        "difficult_negative": 3,
        "authority_version": 0,
        "non_plain_text": 0,
        "general_operations": 4,
    }
    selected: list[dict[str, Any]] = []
    for split in ("validation", "holdout"):
        split_records = [
            record for record in questions if record["topic_id"] in split_topics[split]
        ]
        for category in CATEGORIES:
            candidates = sorted(
                (
                    record
                    for record in split_records
                    if record["primary_category"] == category
                ),
                key=lambda record: record["id"],
            )
            no_answer = [record for record in candidates if not record["answerable"]]
            answerable = [record for record in candidates if record["answerable"]]
            wanted_no_answer = no_answer_targets[category]
            wanted_total = category_targets[split][category]
            chosen = (
                no_answer[:wanted_no_answer]
                + answerable[: wanted_total - wanted_no_answer]
            )
            if len(chosen) != wanted_total:
                raise RepresentativeDatasetError(
                    f"insufficient {split}/{category} gold candidates"
                )
            for record in chosen:
                candidate = dict(record)
                candidate["schema_version"] = GOLD_CANDIDATE_SCHEMA_VERSION
                candidate["proposed_split"] = split
                candidate["selection_reason"] = (
                    "quota-balanced preselection; requires explicit human confirmation"
                )
                selected.append(candidate)
    selected.sort(key=lambda record: (record["proposed_split"], record["id"]))
    if len(selected) != EXPECTED_GOLD_CANDIDATES:
        raise RepresentativeDatasetError("gold candidate count differs from target")
    return selected


def _review_decisions(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": REVIEW_DECISION_SCHEMA_VERSION,
            "candidate_id": candidate["id"],
            "decision": "pending",
            "reviewer": None,
            "reviewed_at": None,
            "overrides": None,
            "notes": "",
        }
        for candidate in candidates
    ]


def _review_decision_errors(
    candidates: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    *,
    require_complete: bool,
) -> list[str]:
    """Check that every decision is explicit and its overrides are auditable."""
    candidate_by_id = {candidate["id"]: candidate for candidate in candidates}
    errors: list[str] = []
    seen: set[str] = set()
    for decision in decisions:
        candidate_id = decision.get("candidate_id")
        if candidate_id in seen:
            errors.append(f"duplicate review decision: {candidate_id}")
        seen.add(candidate_id)
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            errors.append(
                f"review decision references unknown candidate: {candidate_id}"
            )
            continue
        state = decision.get("decision")
        if require_complete and state == "pending":
            errors.append(f"review decision remains pending: {candidate_id}")
        if state == "pending":
            if any(
                decision.get(field) is not None
                for field in ("reviewer", "reviewed_at", "overrides")
            ):
                errors.append(f"pending decision has review metadata: {candidate_id}")
            continue
        if (
            not isinstance(decision.get("reviewer"), str)
            or not decision["reviewer"].strip()
        ):
            errors.append(f"completed decision has no reviewer: {candidate_id}")
        reviewed_at = decision.get("reviewed_at")
        if not isinstance(reviewed_at, str) or not reviewed_at.strip():
            errors.append(f"completed decision has no reviewed_at: {candidate_id}")
        else:
            try:
                parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    errors.append(f"reviewed_at must include timezone: {candidate_id}")
            except ValueError:
                errors.append(f"invalid reviewed_at: {candidate_id}")
        overrides = decision.get("overrides")
        if state in {"approve", "delete"} and overrides is not None:
            errors.append(f"{state} decision cannot contain overrides: {candidate_id}")
        if state == "modify":
            if not isinstance(overrides, Mapping):
                errors.append(f"modify decision has no overrides: {candidate_id}")
                continue
            updates = overrides.get("qrel_grade_updates")
            if not isinstance(updates, list) or not updates:
                errors.append(
                    f"modify decision has no qrel grade updates: {candidate_id}"
                )
                continue
            candidate_qrels = {
                (qrel["document_id"], qrel["chunk_id"]): qrel
                for qrel in candidate["candidate_qrels"]
            }
            update_pairs: set[tuple[str, str]] = set()
            for update in updates:
                if not isinstance(update, Mapping):
                    errors.append(f"invalid qrel grade update: {candidate_id}")
                    continue
                pair = (update.get("document_id"), update.get("chunk_id"))
                if pair in update_pairs:
                    errors.append(f"duplicate qrel grade update: {candidate_id}/{pair}")
                update_pairs.add(pair)
                qrel = candidate_qrels.get(pair)
                if qrel is None:
                    errors.append(
                        f"qrel grade update references unknown qrel: {candidate_id}/{pair}"
                    )
                    continue
                if update.get("from_grade") != qrel["relevance_grade"]:
                    errors.append(
                        f"qrel grade update has stale from_grade: {candidate_id}/{pair}"
                    )
                if update.get("to_grade") == update.get("from_grade"):
                    errors.append(
                        f"qrel grade update is a no-op: {candidate_id}/{pair}"
                    )
        if state in {"modify", "delete"} and not str(decision.get("notes", "")).strip():
            errors.append(f"{state} decision requires notes: {candidate_id}")
    expected = set(candidate_by_id)
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        if missing:
            errors.append(f"missing review decisions: {missing}")
        if extra:
            errors.append(f"unexpected review decisions: {extra}")
    if len(decisions) != len(seen):
        errors.append("review decisions are not one-to-one")
    return errors


def _gold_record(
    candidate: Mapping[str, Any], decision: Mapping[str, Any]
) -> dict[str, Any]:
    qrels = [dict(qrel) for qrel in candidate["candidate_qrels"]]
    if decision["decision"] == "modify":
        by_pair = {(qrel["document_id"], qrel["chunk_id"]): qrel for qrel in qrels}
        for update in decision["overrides"]["qrel_grade_updates"]:
            by_pair[(update["document_id"], update["chunk_id"])]["relevance_grade"] = (
                update["to_grade"]
            )
    if bool(qrels) != candidate["answerable"]:
        raise RepresentativeDatasetError(
            f"reviewed answerability/qrels mismatch: {candidate['id']}"
        )
    return {
        "schema_version": GOLD_DATASET_SCHEMA_VERSION,
        "id": candidate["id"],
        "question": candidate["question"],
        "answerable": candidate["answerable"],
        "primary_category": candidate["primary_category"],
        "secondary_categories": list(candidate["secondary_categories"]),
        "topic_id": candidate["topic_id"],
        "fact_family_id": candidate["fact_family_id"],
        "qrels": qrels,
        "split": candidate["proposed_split"],
        "label_provenance": "human_review",
        "ambiguity_state": candidate["ambiguity_state"],
        "privacy_state": "synthetic_safe_confirmed",
        "authority_decision": "confirmed",
        "review_status": "human_confirmed",
        "review_decision": decision["decision"],
        "reviewer": decision["reviewer"],
        "reviewed_at": decision["reviewed_at"],
        "notes": decision["notes"],
    }


def _build_gold_dataset(
    candidates: Sequence[Mapping[str, Any]], decisions: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    decision_by_id = {decision["candidate_id"]: decision for decision in decisions}
    return [
        _gold_record(candidate, decision_by_id[candidate["id"]])
        for candidate in candidates
        if decision_by_id[candidate["id"]]["decision"] != "delete"
    ]


def _render_review_batch(
    candidates: Sequence[Mapping[str, Any]],
    batch_number: int,
    documents: Sequence[Mapping[str, Any]],
) -> str:
    filenames = {document["id"]: document["filename"] for document in documents}
    lines = [
        f"# DS-04 Human Review Batch {batch_number}",
        "",
        f"Cases: {len(candidates)}. Every case remains `assisted_unverified` until a human decision is recorded.",
        "",
        "For each case, review the question, answerability, ambiguity and every proposed qrel. Record approve, modify or delete in `review_decisions.jsonl`; a batch-level approval is valid only after every case below has been inspected.",
        "",
    ]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"## {index}. {candidate['id']}",
                "",
                f"- Proposed split: `{candidate['proposed_split']}`",
                f"- Category: `{candidate['primary_category']}`",
                f"- Question: {candidate['question']}",
                f"- Answerable: `{str(candidate['answerable']).lower()}`",
                f"- Ambiguity: `{candidate['ambiguity_state']}`",
                f"- Privacy: `{candidate['privacy_state']}`",
            ]
        )
        if candidate["candidate_qrels"]:
            lines.append("- Proposed qrels:")
            for qrel in candidate["candidate_qrels"]:
                lines.append(
                    f"  - source `{filenames[qrel['document_id']]}` / "
                    f"document `{qrel['document_id']}` / chunk `{qrel['chunk_id']}` / "
                    f"grade `{qrel['relevance_grade']}` / control "
                    f"`{qrel['evidence_control_id']}` / quote: {qrel['evidence_quote']}"
                )
        else:
            lines.append("- Proposed qrels: none (no-answer)")
        lines.extend(
            [
                "- Human decision: `[ ] approve  [ ] modify  [ ] delete`",
                "- Reviewer note:",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _privacy_findings(texts: Iterable[tuple[str, str]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for source, text in texts:
        for pattern_name, pattern in (
            ("credential", _CREDENTIAL_PATTERNS[0]),
            ("bearer", _CREDENTIAL_PATTERNS[1]),
            ("secret_assignment", _CREDENTIAL_PATTERNS[2]),
            ("phone", _PHONE_PATTERN),
            ("email", _EMAIL_PATTERN),
        ):
            if pattern.search(text):
                findings.append({"source": source, "type": pattern_name})
    return findings


def _counts_by(records: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(record[field]) for record in records).items()))


def _snapshot(
    design_sha256: str,
    document_records: Sequence[Mapping[str, Any]],
    chunk_records: Sequence[Mapping[str, Any]],
    exploration: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    outputs: Mapping[str, Mapping[str, Any]],
    review_packets: Mapping[str, Mapping[str, Any]],
    document_tree_sha256: str,
    *,
    decisions: Sequence[Mapping[str, Any]] | None = None,
    gold_dataset: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    chunk_counts = [int(record["chunk_count"]) for record in document_records]
    split_counts = _counts_by(candidates, "proposed_split")
    no_answer_by_split = {
        split: sum(
            not record["answerable"]
            for record in candidates
            if record["proposed_split"] == split
        )
        for split in ("validation", "holdout")
    }
    final = gold_dataset is not None
    fingerprints = {name: value["sha256"] for name, value in outputs.items()}
    fingerprints["documents_tree_sha256"] = document_tree_sha256
    fingerprints["review_packets"] = {
        name: value["sha256"] for name, value in review_packets.items()
    }
    fingerprints["dataset_sha256"] = canonical_sha256(
        {
            "design_sha256": design_sha256,
            "fingerprints": fingerprints,
            "generation": {
                "chunk_overlap": CHUNK_OVERLAP,
                "chunk_size": CHUNK_SIZE,
                "generator": "documind-representative-rule-builder-v1",
            },
        }
    )
    if final:
        status = FINAL_SNAPSHOT_STATUS
        label_policy = "human_confirmed_gold_after_explicit_review"
        review_counts = Counter(decision["decision"] for decision in decisions or ())
        human_review = {
            "required": EXPECTED_GOLD_CANDIDATES,
            "approved": review_counts.get("approve", 0),
            "modified": review_counts.get("modify", 0),
            "deleted": review_counts.get("delete", 0),
            "pending": review_counts.get("pending", 0),
            "privacy_decision": "confirmed",
            "authority_decision": "confirmed",
        }
    else:
        status = "awaiting_human_review"
        label_policy = "assisted_unverified_until_explicit_human_confirmation"
        human_review = {
            "required": EXPECTED_GOLD_CANDIDATES,
            "approved": 0,
            "modified": 0,
            "deleted": 0,
            "pending": EXPECTED_GOLD_CANDIDATES,
            "privacy_decision": "pending_human",
            "authority_decision": "pending_human",
        }
    counts = {
        "topics": EXPECTED_TOPICS,
        "documents": len(document_records),
        "chunks": len(chunk_records),
        "exploration_questions": len(exploration),
        "gold_candidates": len(candidates),
        "review_pending": human_review["pending"],
    }
    if final:
        counts["gold_dataset"] = len(gold_dataset or ())
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "dataset_id": "p2-retrieval-v2",
        "status": status,
        "design_sha256": design_sha256,
        "generation": {
            "generator": "documind-representative-rule-builder-v1",
            "chunker": "RecursiveCharacterTextSplitter:v1",
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "label_policy": label_policy,
        },
        "counts": counts,
        "shape": {
            "minimum_chunks_per_document": min(chunk_counts),
            "median_chunks_per_document": statistics.median(chunk_counts),
            "maximum_chunks_per_document": max(chunk_counts),
            "authority_counts": _counts_by(document_records, "authority_state"),
            "format_counts": _counts_by(document_records, "source_format"),
            "exploration_category_counts": _counts_by(exploration, "primary_category"),
            "gold_category_counts": _counts_by(candidates, "primary_category"),
            "gold_split_counts": split_counts,
            "gold_no_answer_by_split": no_answer_by_split,
        },
        "outputs": {
            name: {
                "path": f"{name}.jsonl",
                "count": value["count"],
                "sha256": value["sha256"],
            }
            for name, value in outputs.items()
        },
        "review_packets": dict(review_packets),
        "documents_tree_sha256": document_tree_sha256,
        "fingerprints": fingerprints,
        "human_review": human_review,
    }


def _document_tree_hash(documents_root: Path) -> str:
    return canonical_sha256(
        [
            {"path": path.name, "sha256": sha256_file(path)}
            for path in sorted(documents_root.glob("*.txt"), key=lambda item: item.name)
        ]
    )


def _guard_output_root(output_root: Path, replace: bool) -> None:
    resolved = output_root.resolve()
    if resolved in {Path.cwd().resolve(), Path(resolved.anchor)}:
        raise RepresentativeDatasetError(
            f"unsafe representative output root: {output_root}"
        )
    if not output_root.exists() or not any(output_root.iterdir()):
        return
    if not replace:
        raise FileExistsError(
            f"representative output is not empty; pass replace=True: {output_root}"
        )
    marker = output_root / "representative_snapshot.json"
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise RepresentativeDatasetError(
            f"refusing to replace unowned representative output: {output_root}"
        ) from exc
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise RepresentativeDatasetError(
            f"refusing to replace unowned representative output: {output_root}"
        )


def _publish(staging: Path, output_root: Path, replace: bool) -> None:
    _guard_output_root(output_root, replace)
    backup: Path | None = None
    try:
        if output_root.exists():
            backup = output_root.with_name(f".{output_root.name}.backup-{os.getpid()}")
            if backup.exists():
                raise FileExistsError(f"representative backup exists: {backup}")
            output_root.replace(backup)
        staging.replace(output_root)
    except BaseException:
        if backup is not None and backup.exists() and not output_root.exists():
            backup.replace(output_root)
        raise
    else:
        if backup is not None:
            shutil.rmtree(backup)


def _render_readme(snapshot: Mapping[str, Any]) -> str:
    if snapshot["status"] == FINAL_SNAPSHOT_STATUS:
        human_review = snapshot["human_review"]
        gold_count = snapshot["counts"]["gold_dataset"]
        review_summary = (
            f"Human review: {human_review['approved']} approve, "
            f"{human_review['modified']} modify, "
            f"{human_review['deleted']} delete, "
            f"{human_review['pending']} pending."
        )
        gold_note = (
            f"`gold_dataset.jsonl` contains {gold_count} retained cases. "
            "Every retained case has explicit human confirmation; modified qrels "
            "retain their audit trail in `review_decisions.jsonl`."
        )
        status = "GOLD CONFIRMED"
    else:
        review_summary = "Human review: all 100 decisions are pending."
        gold_note = (
            "`exploration.jsonl` and `gold_candidates.jsonl` are not golden labels. "
            "A final `gold_dataset.jsonl` must not exist until every retained candidate, "
            "qrel, ambiguity state, privacy decision and authority decision has explicit "
            "human confirmation."
        )
        status = "AWAITING HUMAN REVIEW"
    return f"""# P2 Retrieval V2 Representative Dataset

Status: `{status}`

This directory contains project-generated synthetic DocuMind operational material. It contains no private or production documents. The 75 documents cover 25 topics with active, draft and superseded variants and are chunked with the production `500/100` recursive policy.

- Documents: {snapshot['counts']['documents']}
- Chunks: {snapshot['counts']['chunks']}
- Exploration pool: {snapshot['counts']['exploration_questions']} assisted/unverified questions
- Gold candidates: {snapshot['counts']['gold_candidates']}
- Dataset SHA-256: `{snapshot['fingerprints']['dataset_sha256']}`

{review_summary}

{gold_note}

Review packets are split into `review_batch_1.md` and `review_batch_2.md`; machine-readable decisions are in `review_decisions.jsonl`. DS-05 split isolation and fingerprint freeze can begin only after the DS-04 gate is explicitly approved.
"""


def build_representative_dataset(
    design_path: Path = DEFAULT_DESIGN,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    design_path = Path(design_path)
    output_root = Path(output_root)
    design = load_design(design_path)
    _guard_output_root(output_root, replace)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_root.parent)
    )
    try:
        documents, chunks, document_ids = _build_documents(design["topics"], staging)
        exploration = _build_questions(design["topics"], document_ids, chunks)
        candidates = _select_gold_candidates(exploration)
        decisions = _review_decisions(candidates)
        output_records = {
            "documents": documents,
            "chunks": [
                {
                    key: value
                    for key, value in record.items()
                    if key != "content_preview_source"
                }
                for record in chunks
            ],
            "exploration": exploration,
            "gold_candidates": candidates,
            "review_decisions": decisions,
        }
        outputs = {
            name: _write_jsonl(staging / f"{name}.jsonl", records)
            for name, records in output_records.items()
        }
        validation_texts = [
            (
                record["filename"],
                (staging / "documents" / record["filename"]).read_text(
                    encoding="utf-8"
                ),
            )
            for record in documents
        ] + [(record["id"], record["question"]) for record in exploration]
        privacy_findings = _privacy_findings(validation_texts)
        if privacy_findings:
            raise RepresentativeDatasetError(
                f"privacy/credential scan failed: {privacy_findings[:5]}"
            )
        batch_one = candidates[:50]
        batch_two = candidates[50:]
        review_batches = {
            "review_batch_1": (batch_one, 1),
            "review_batch_2": (batch_two, 2),
        }
        review_packets: dict[str, dict[str, Any]] = {}
        for name, (batch, batch_number) in review_batches.items():
            path = staging / f"{name}.md"
            path.write_text(
                _render_review_batch(batch, batch_number, documents),
                encoding="utf-8",
                newline="\n",
            )
            review_packets[name] = {
                "path": path.name,
                "count": len(batch),
                "sha256": sha256_file(path),
            }
        snapshot = _snapshot(
            sha256_file(design_path),
            documents,
            output_records["chunks"],
            exploration,
            candidates,
            outputs,
            review_packets,
            _document_tree_hash(staging / "documents"),
        )
        _write_json(staging / "representative_snapshot.json", snapshot)
        (staging / "README.md").write_text(
            _render_readme(snapshot), encoding="utf-8", newline="\n"
        )
        _publish(staging, output_root, replace)
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "snapshot": snapshot,
            "snapshot_file_sha256": sha256_file(
                output_root / "representative_snapshot.json"
            ),
            "privacy_findings": privacy_findings,
        }
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def finalize_representative_dataset(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    contract_root: Path = DEFAULT_CONTRACT_ROOT,
) -> dict[str, Any]:
    """Apply explicit human decisions and atomically publish the gold dataset."""
    output_root = Path(output_root)
    contract_root = Path(contract_root)
    snapshot_path = output_root / "representative_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if snapshot.get("status") != "awaiting_human_review":
        raise RepresentativeDatasetError("representative dataset is already finalized")

    pre_validation = validate_representative_dataset(
        output_root, contract_root, allow_completed_review=True
    )
    if not pre_validation["ok"]:
        raise RepresentativeDatasetError(
            f"cannot finalize invalid pre-review dataset: {pre_validation['errors']}"
        )
    candidates = _load_jsonl(output_root / "gold_candidates.jsonl")
    decisions = _load_jsonl(output_root / "review_decisions.jsonl")
    decision_errors = _review_decision_errors(
        candidates, decisions, require_complete=True
    )
    if decision_errors:
        raise RepresentativeDatasetError(
            f"human review is incomplete or invalid: {decision_errors}"
        )
    gold_dataset = _build_gold_dataset(candidates, decisions)
    if not gold_dataset:
        raise RepresentativeDatasetError("human review retained no gold cases")

    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.final-", dir=output_root.parent)
    )
    shutil.rmtree(staging)
    try:
        shutil.copytree(output_root, staging)
        review_result = _write_jsonl(staging / "review_decisions.jsonl", decisions)
        gold_result = _write_jsonl(staging / "gold_dataset.jsonl", gold_dataset)
        records = {
            name: _load_jsonl(staging / f"{name}.jsonl")
            for name in ("documents", "chunks", "exploration", "gold_candidates")
        }
        outputs = {
            name: {
                "count": len(records[name]),
                "sha256": sha256_file(staging / f"{name}.jsonl"),
            }
            for name in ("documents", "chunks", "exploration", "gold_candidates")
        }
        outputs["review_decisions"] = review_result
        outputs["gold_dataset"] = gold_result
        review_packets = {
            name: {
                "path": snapshot["review_packets"][name]["path"],
                "count": snapshot["review_packets"][name]["count"],
                "sha256": sha256_file(
                    staging / snapshot["review_packets"][name]["path"]
                ),
            }
            for name in ("review_batch_1", "review_batch_2")
        }
        final_snapshot = _snapshot(
            snapshot["design_sha256"],
            records["documents"],
            records["chunks"],
            records["exploration"],
            records["gold_candidates"],
            outputs,
            review_packets,
            _document_tree_hash(staging / "documents"),
            decisions=decisions,
            gold_dataset=gold_dataset,
        )
        _write_json(staging / "representative_snapshot.json", final_snapshot)
        (staging / "README.md").write_text(
            _render_readme(final_snapshot), encoding="utf-8", newline="\n"
        )
        _publish(staging, output_root, replace=True)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    result = {
        "schema_version": FINAL_EVIDENCE_SCHEMA_VERSION,
        "snapshot": final_snapshot,
        "validation": validate_representative_dataset(output_root, contract_root),
        "modified_candidate_ids": [
            decision["candidate_id"]
            for decision in decisions
            if decision["decision"] == "modify"
        ],
    }
    return result


def _quota_errors(
    documents: Sequence[Mapping[str, Any]],
    exploration: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if len(documents) != EXPECTED_DOCUMENTS:
        errors.append(f"document count {len(documents)} != {EXPECTED_DOCUMENTS}")
    chunk_counts = [int(record["chunk_count"]) for record in documents]
    if not chunk_counts or statistics.median(chunk_counts) < 3:
        errors.append("median chunks per document is below 3")
    if len(exploration) != EXPECTED_EXPLORATION:
        errors.append(f"exploration count {len(exploration)} != {EXPECTED_EXPLORATION}")
    if len(candidates) != EXPECTED_GOLD_CANDIDATES:
        errors.append(
            f"gold candidate count {len(candidates)} != {EXPECTED_GOLD_CANDIDATES}"
        )
    for split in ("validation", "holdout"):
        split_records = [
            record for record in candidates if record["proposed_split"] == split
        ]
        if len(split_records) != 50:
            errors.append(f"{split} candidate count is not 50")
        no_answer = sum(not record["answerable"] for record in split_records)
        if no_answer / max(len(split_records), 1) < 0.25:
            errors.append(f"{split} no-answer rate is below 25%")
    category_counts = Counter(record["primary_category"] for record in candidates)
    minimums = {
        "exact_lexical": 15,
        "semantic": 15,
        "difficult_negative": 20,
        "authority_version": 10,
        "non_plain_text": 10,
    }
    for category, minimum in minimums.items():
        if category_counts[category] < minimum:
            errors.append(f"{category} count is below {minimum}")
    topic_splits: dict[str, set[str]] = defaultdict(set)
    for record in candidates:
        topic_splits[record["topic_id"]].add(record["proposed_split"])
    leaked = sorted(topic for topic, splits in topic_splits.items() if len(splits) > 1)
    if leaked:
        errors.append(f"topic families cross proposed splits: {leaked}")
    return errors


def validate_representative_dataset(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    contract_root: Path = DEFAULT_CONTRACT_ROOT,
    *,
    allow_completed_review: bool = False,
) -> dict[str, Any]:
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError
    except ImportError as exc:
        raise RepresentativeDatasetError(
            "jsonschema is required for representative dataset validation"
        ) from exc
    output_root = Path(output_root)
    schemas = {
        name: json.loads((Path(contract_root) / filename).read_text(encoding="utf-8"))
        for name, filename in _QUESTION_SCHEMA_FILES.items()
    }
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    snapshot = json.loads(
        (output_root / "representative_snapshot.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schemas["snapshot"]).validate(snapshot)
    records = {
        name: _load_jsonl(output_root / f"{name}.jsonl")
        for name in (
            "documents",
            "chunks",
            "exploration",
            "gold_candidates",
            "review_decisions",
        )
    }
    gold_path = output_root / "gold_dataset.jsonl"
    if gold_path.exists():
        records["gold_dataset"] = _load_jsonl(gold_path)
    errors: list[str] = []
    record_names = (
        "documents",
        "chunks",
        "exploration",
        "gold_candidates",
        "review_decisions",
    ) + (("gold_dataset",) if "gold_dataset" in records else ())
    for name in record_names:
        validator = Draft202012Validator(schemas[name])
        for index, record in enumerate(records[name]):
            try:
                validator.validate(record)
            except ValidationError as exc:
                errors.append(f"{name}[{index}] schema: {exc.message}")
    document_ids = {record["id"] for record in records["documents"]}
    chunk_ids = {record["id"] for record in records["chunks"]}
    chunk_documents = {
        record["id"]: record["document_id"] for record in records["chunks"]
    }
    if len(document_ids) != len(records["documents"]):
        errors.append("duplicate representative document IDs")
    if len(chunk_ids) != len(records["chunks"]):
        errors.append("duplicate representative chunk IDs")
    exploration_ids = {record["id"] for record in records["exploration"]}
    candidate_ids = {record["id"] for record in records["gold_candidates"]}
    if len(exploration_ids) != len(records["exploration"]):
        errors.append("duplicate exploration IDs")
    if len(candidate_ids) != len(records["gold_candidates"]):
        errors.append("duplicate gold candidate IDs")
    if not candidate_ids <= exploration_ids:
        errors.append("gold candidate is absent from exploration pool")
    normalized_questions = {
        re.sub(r"\s+", " ", record["question"].strip().casefold())
        for record in records["exploration"]
    }
    if len(normalized_questions) != len(records["exploration"]):
        errors.append("duplicate normalized exploration questions")
    exploration_by_id = {record["id"]: record for record in records["exploration"]}
    for candidate in records["gold_candidates"]:
        source = exploration_by_id.get(candidate["id"])
        if source is None:
            continue
        candidate_source = {
            key: value
            for key, value in candidate.items()
            if key not in {"proposed_split", "selection_reason"}
        }
        candidate_source["schema_version"] = EXPLORATION_SCHEMA_VERSION
        if candidate_source != source:
            errors.append(
                f"gold candidate differs from exploration source: {candidate['id']}"
            )
    for record in (*records["exploration"], *records["gold_candidates"]):
        if record["answerable"] != bool(record["candidate_qrels"]):
            errors.append(f"answerability/qrels mismatch: {record['id']}")
        seen_pairs: set[tuple[str, str]] = set()
        for qrel in record["candidate_qrels"]:
            pair = (qrel["document_id"], qrel["chunk_id"])
            if pair in seen_pairs:
                errors.append(f"duplicate qrel pair: {record['id']}/{pair}")
            seen_pairs.add(pair)
            if qrel["document_id"] not in document_ids:
                errors.append(f"unknown qrel document: {record['id']}")
            if qrel["chunk_id"] not in chunk_ids:
                errors.append(f"unknown qrel chunk: {record['id']}")
            elif chunk_documents[qrel["chunk_id"]] != qrel["document_id"]:
                errors.append(f"qrel document/chunk mismatch: {record['id']}")
    is_final = snapshot.get("status") == FINAL_SNAPSHOT_STATUS
    if is_final != ("gold_dataset" in records):
        errors.append("snapshot status and gold_dataset presence disagree")
    decision_ids = [record["candidate_id"] for record in records["review_decisions"]]
    if set(decision_ids) != candidate_ids or len(decision_ids) != len(
        set(decision_ids)
    ):
        errors.append("review decisions do not map one-to-one to candidates")
    errors.extend(
        _review_decision_errors(
            records["gold_candidates"],
            records["review_decisions"],
            require_complete=is_final,
        )
    )
    if (
        not is_final
        and not allow_completed_review
        and any(
            record["decision"] != "pending" for record in records["review_decisions"]
        )
    ):
        errors.append("pre-review decisions must all remain pending")
    errors.extend(
        _quota_errors(
            records["documents"],
            records["exploration"],
            records["gold_candidates"],
        )
    )
    document_texts = [
        (
            record["filename"],
            (output_root / "documents" / record["filename"]).read_text(
                encoding="utf-8"
            ),
        )
        for record in records["documents"]
    ]
    findings = _privacy_findings(document_texts)
    if findings:
        errors.append(f"privacy findings: {findings[:5]}")
    regenerated_chunks: list[dict[str, Any]] = []
    regenerated_chunk_content: dict[str, str] = {}
    chunker = DocumentChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    for document in records["documents"]:
        document_path = output_root / "documents" / document["filename"]
        content = document_path.read_text(encoding="utf-8")
        if (
            hashlib.sha256(content.encode("utf-8")).hexdigest()
            != document["content_sha256"]
        ):
            errors.append(f"document content fingerprint mismatch: {document['id']}")
        chunks = chunker.chunk_documents_recursive(
            [
                Document(
                    page_content=content,
                    metadata={
                        "document_id": document["id"],
                        "source_file": document["filename"],
                    },
                )
            ]
        )
        if len(chunks) != document["chunk_count"]:
            errors.append(f"document chunk count mismatch: {document['id']}")
        regenerated_chunks.extend(
            {
                "schema_version": CHUNK_SCHEMA_VERSION,
                "id": chunk.metadata["chunk_id"],
                "document_id": document["id"],
                "chunk_index": chunk.metadata["chunk_index"],
                "char_count": len(chunk.page_content),
                "content_sha256": hashlib.sha256(
                    chunk.page_content.encode("utf-8")
                ).hexdigest(),
            }
            for chunk in chunks
        )
        regenerated_chunk_content.update(
            {chunk.metadata["chunk_id"]: chunk.page_content for chunk in chunks}
        )
    if regenerated_chunks != records["chunks"]:
        errors.append("stored chunks differ from production chunker rebuild")
    for record in (*records["exploration"], *records["gold_candidates"]):
        for qrel in record["candidate_qrels"]:
            content = regenerated_chunk_content.get(qrel["chunk_id"], "")
            if qrel["evidence_control_id"] not in content:
                errors.append(
                    f"qrel control marker is absent from chunk: {record['id']}"
                )
            if qrel["evidence_quote"] not in content:
                errors.append(
                    f"qrel evidence quote is absent from chunk: {record['id']}"
                )
    if is_final:
        expected_gold = _build_gold_dataset(
            records["gold_candidates"], records["review_decisions"]
        )
        if records.get("gold_dataset") != expected_gold:
            errors.append("gold_dataset.jsonl differs from reviewed decisions")
        gold_ids = {record["id"] for record in records.get("gold_dataset", ())}
        if not gold_ids <= candidate_ids:
            errors.append("gold dataset contains an unknown candidate")
        if len(gold_ids) != len(records.get("gold_dataset", ())):
            errors.append("duplicate gold dataset IDs")
        review_counts = Counter(
            decision["decision"] for decision in records["review_decisions"]
        )
        expected_review = snapshot["human_review"]
        review_key_by_decision = {
            "approve": "approved",
            "modify": "modified",
            "delete": "deleted",
            "pending": "pending",
        }
        for decision_name, review_key in review_key_by_decision.items():
            if expected_review[review_key] != review_counts.get(decision_name, 0):
                errors.append(f"human review count mismatch: {decision_name}")
        if len(records.get("gold_dataset", ())) != (
            review_counts.get("approve", 0) + review_counts.get("modify", 0)
        ):
            errors.append("gold dataset count does not match retained decisions")
        if expected_review["pending"] != 0:
            errors.append("final snapshot still has pending review decisions")
        if expected_review["privacy_decision"] != "confirmed":
            errors.append("final privacy decision is not confirmed")
        if expected_review["authority_decision"] != "confirmed":
            errors.append("final authority decision is not confirmed")
        if (
            _counts_by(records.get("gold_dataset", ()), "primary_category")
            != snapshot["shape"]["gold_category_counts"]
        ):
            errors.append("gold category counts differ from candidate quotas")
        if (
            _counts_by(records.get("gold_dataset", ()), "split")
            != snapshot["shape"]["gold_split_counts"]
        ):
            errors.append("gold split counts differ from candidate quotas")
        gold_no_answer_by_split = {
            split: sum(
                not record["answerable"]
                for record in records.get("gold_dataset", ())
                if record["split"] == split
            )
            for split in ("validation", "holdout")
        }
        if gold_no_answer_by_split != snapshot["shape"]["gold_no_answer_by_split"]:
            errors.append("gold no-answer counts differ from candidate quotas")
        for record in records.get("gold_dataset", ()):
            if record["answerable"] != bool(record["qrels"]):
                errors.append(f"gold answerability/qrels mismatch: {record['id']}")
            seen_pairs: set[tuple[str, str]] = set()
            for qrel in record["qrels"]:
                pair = (qrel["document_id"], qrel["chunk_id"])
                if pair in seen_pairs:
                    errors.append(f"duplicate gold qrel pair: {record['id']}/{pair}")
                seen_pairs.add(pair)
                if qrel["document_id"] not in document_ids:
                    errors.append(f"unknown gold qrel document: {record['id']}")
                if qrel["chunk_id"] not in chunk_ids:
                    errors.append(f"unknown gold qrel chunk: {record['id']}")
                elif chunk_documents[qrel["chunk_id"]] != qrel["document_id"]:
                    errors.append(f"gold qrel document/chunk mismatch: {record['id']}")
                content = regenerated_chunk_content.get(qrel["chunk_id"], "")
                if qrel["evidence_control_id"] not in content:
                    errors.append(f"gold qrel control marker is absent: {record['id']}")
                if qrel["evidence_quote"] not in content:
                    errors.append(f"gold qrel evidence quote is absent: {record['id']}")
    elif "gold_dataset" in records:
        errors.append("gold_dataset.jsonl exists before human review completion")
    expected_output_names = {
        "documents",
        "chunks",
        "exploration",
        "gold_candidates",
        "review_decisions",
    }
    if is_final:
        expected_output_names.add("gold_dataset")
    if set(snapshot["outputs"]) != expected_output_names:
        errors.append("snapshot output set does not match review status")
    for name, output in snapshot["outputs"].items():
        if name not in records:
            errors.append(f"snapshot output has no local records: {name}")
            continue
        path = output_root / output["path"]
        if (
            not (allow_completed_review and name == "review_decisions")
            and sha256_file(path) != output["sha256"]
        ):
            errors.append(f"snapshot fingerprint mismatch: {name}")
        if len(records[name]) != output["count"]:
            errors.append(f"snapshot count mismatch: {name}")
    for name, packet in snapshot["review_packets"].items():
        path = output_root / packet["path"]
        if sha256_file(path) != packet["sha256"]:
            errors.append(f"review packet fingerprint mismatch: {name}")
        if path.read_text(encoding="utf-8").count("\n## ") != packet["count"]:
            errors.append(f"review packet case count mismatch: {name}")
    if (
        _document_tree_hash(output_root / "documents")
        != snapshot["documents_tree_sha256"]
    ):
        errors.append("document tree fingerprint mismatch")
    fingerprint_payload = {
        "design_sha256": snapshot["design_sha256"],
        "fingerprints": {
            key: value
            for key, value in snapshot["fingerprints"].items()
            if key != "dataset_sha256"
        },
        "generation": {
            "chunk_overlap": snapshot["generation"]["chunk_overlap"],
            "chunk_size": snapshot["generation"]["chunk_size"],
            "generator": snapshot["generation"]["generator"],
        },
    }
    if (
        canonical_sha256(fingerprint_payload)
        != snapshot["fingerprints"]["dataset_sha256"]
    ):
        errors.append("aggregate dataset fingerprint mismatch")
    return {
        "ok": not errors,
        "errors": errors,
        "counts": snapshot["counts"],
        "shape": snapshot["shape"],
        "human_review": snapshot["human_review"],
    }


def render_evidence_markdown(evidence: Mapping[str, Any]) -> str:
    snapshot = evidence["snapshot"]
    counts = snapshot["counts"]
    shape = snapshot["shape"]
    return f"""# P2 DS-04 Pre-Review Evidence

- Status: `{snapshot['status']}`
- Documents: {counts['documents']}
- Chunks: {counts['chunks']}
- Median chunks/document: {shape['median_chunks_per_document']}
- Exploration questions: {counts['exploration_questions']}
- Gold candidates: {counts['gold_candidates']}
- Validation/Holdout: {shape['gold_split_counts']['validation']} / {shape['gold_split_counts']['holdout']}
- No-answer by split: {shape['gold_no_answer_by_split']['validation']} / {shape['gold_no_answer_by_split']['holdout']}
- Dataset SHA-256: `{snapshot['fingerprints']['dataset_sha256']}`
- Privacy scan findings: {len(evidence['privacy_findings'])}

This is pre-review evidence only. All labels remain `assisted_unverified`; no final gold set or production benefit claim exists until the human review decisions are complete and DS-04 is reviewed.
"""


def render_final_evidence_markdown(
    evidence: Mapping[str, Any], output_root: Path = DEFAULT_OUTPUT_ROOT
) -> str:
    snapshot = evidence["snapshot"]
    counts = snapshot["counts"]
    review = snapshot["human_review"]
    modifications = evidence.get("modified_candidate_ids")
    if modifications is None:
        modifications = [
            decision["candidate_id"]
            for decision in _load_jsonl(Path(output_root) / "review_decisions.jsonl")
            if decision["decision"] == "modify"
        ]
    return f"""# P2 DS-04 Final Review Evidence

- Status: `{snapshot['status']}`
- Documents: {counts['documents']}
- Chunks: {counts['chunks']}
- Exploration questions: {counts['exploration_questions']}
- Gold candidates: {counts['gold_candidates']}
- Retained gold cases: {counts['gold_dataset']}
- Human review: {review['approved']} approve / {review['modified']} modify / {review['deleted']} delete / {review['pending']} pending
- Modified candidates: {', '.join(modifications) if modifications else 'none'}
- Dataset SHA-256: `{snapshot['fingerprints']['dataset_sha256']}`

All retained cases have explicit human confirmation for answerability, qrels, grades, ambiguity, authority and privacy. Modified qrels are recorded in `review_decisions.jsonl`; the formal gold records are in `gold_dataset.jsonl`. DS-05 remains gated on explicit user approval.
"""


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate", "finalize"))
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--contract-root", type=Path, default=DEFAULT_CONTRACT_ROOT)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-markdown", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            evidence = build_representative_dataset(
                args.design, args.output_root, replace=args.replace
            )
            validation = validate_representative_dataset(
                args.output_root, args.contract_root
            )
            if not validation["ok"]:
                raise RepresentativeDatasetError(
                    f"post-build validation failed: {validation['errors']}"
                )
            evidence["validation"] = validation
            if args.report_json:
                _write_json(args.report_json, evidence)
            if args.report_markdown:
                args.report_markdown.parent.mkdir(parents=True, exist_ok=True)
                args.report_markdown.write_text(
                    render_evidence_markdown(evidence),
                    encoding="utf-8",
                    newline="\n",
                )
            result = evidence
        elif args.command == "finalize":
            result = finalize_representative_dataset(
                args.output_root, args.contract_root
            )
            if args.report_json:
                _write_json(args.report_json, result)
            if args.report_markdown:
                args.report_markdown.parent.mkdir(parents=True, exist_ok=True)
                args.report_markdown.write_text(
                    render_final_evidence_markdown(result, args.output_root),
                    encoding="utf-8",
                    newline="\n",
                )
        else:
            result = validate_representative_dataset(
                args.output_root, args.contract_root
            )
    except (
        FileNotFoundError,
        RepresentativeDatasetError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"DS-04 representative dataset: ERROR\n- {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", result.get("validation", {}).get("ok", True)) else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
