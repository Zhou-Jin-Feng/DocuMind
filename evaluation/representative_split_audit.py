"""Audit and freeze the DS-04 validation/holdout split boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Mapping

from evaluation.representative_dataset import (
    DEFAULT_CONTRACT_ROOT,
    DEFAULT_OUTPUT_ROOT,
    RepresentativeDatasetError,
    canonical_sha256,
    validate_representative_dataset,
)

SPLITS = ("validation", "holdout")
SCHEMA_VERSION = "p2-ds05-split-freeze-v1"
AUDIT_SCHEMA_VERSION = "p2-ds05-split-audit-v1"
ALGORITHM_VERSION = "question-near-duplicate-v1"
NEAR_DUPLICATE_THRESHOLD = 0.95
DEFAULT_FREEZE = DEFAULT_OUTPUT_ROOT / "split_freeze.json"
DEFAULT_AUDIT_JSON = (
    Path(__file__).resolve().parent / "reports" / "p2_ds05_split_audit_v1.json"
)
DEFAULT_AUDIT_MARKDOWN = (
    Path(__file__).resolve().parent / "reports" / "p2_ds05_split_audit_v1.md"
)


class SplitAuditError(ValueError):
    """Raised when the representative split cannot be audited or frozen."""


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"DS-05 文件不存在: {path}")
    return _sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SplitAuditError(f"无法读取 JSON 工件: {path}") from exc
    if not isinstance(value, dict):
        raise SplitAuditError(f"JSON 工件必须是对象: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"DS-05 JSONL 不存在: {path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SplitAuditError(f"JSONL 第 {line_number} 行无效: {path}") from exc
        if not isinstance(record, dict):
            raise SplitAuditError(f"JSONL 第 {line_number} 行必须是对象: {path}")
        records.append(record)
    return records


def _validate_artifact_schema(
    value: Mapping[str, Any], contract_root: Path, filename: str
) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise SplitAuditError(
            "jsonschema is required for DS-05 artifact validation"
        ) from exc
    schema = _load_json(Path(contract_root) / filename)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        location = ".".join(str(part) for part in errors[0].absolute_path) or "$"
        raise SplitAuditError(
            f"DS-05 {filename} schema error at {location}: {errors[0].message}"
        )


def _normalise_question(question: str) -> str:
    """Normalize questions for exact and high-confidence near-duplicate checks."""

    normalized = unicodedata.normalize("NFKC", question).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _question_similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None, _normalise_question(left), _normalise_question(right)
    ).ratio()


def _digest_strings(values: Iterable[str]) -> str:
    return canonical_sha256(sorted(values))


def _digest_records(records: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        encoded = _canonical_json_bytes(record)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _pair_key(qrel: Mapping[str, Any]) -> str:
    return f"{qrel['document_id']}::{qrel['chunk_id']}"


def _split_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    question_hashes = [
        canonical_sha256(
            {
                "id": record["id"],
                "question": _normalise_question(record["question"]),
            }
        )
        for record in records
    ]
    qrel_pairs = sorted(
        {_pair_key(qrel) for record in records for qrel in record["qrels"]}
    )
    evidence_quote_hashes = sorted(
        {
            canonical_sha256(qrel["evidence_quote"])
            for record in records
            for qrel in record["qrels"]
        }
    )
    return {
        "count": len(records),
        "case_ids": [record["id"] for record in records],
        "fact_family_ids": sorted({record["fact_family_id"] for record in records}),
        "topic_ids": sorted({record["topic_id"] for record in records}),
        "document_ids": sorted(
            {qrel["document_id"] for record in records for qrel in record["qrels"]}
        ),
        "chunk_ids": sorted(
            {qrel["chunk_id"] for record in records for qrel in record["qrels"]}
        ),
        "qrel_pair_ids": qrel_pairs,
        "evidence_control_ids": sorted(
            {
                qrel["evidence_control_id"]
                for record in records
                for qrel in record["qrels"]
            }
        ),
        "evidence_quote_hashes": evidence_quote_hashes,
        "question_hashes": question_hashes,
        "records_sha256": _digest_records(records),
        "questions_sha256": _digest_strings(question_hashes),
        "qrel_pairs_sha256": _digest_strings(qrel_pairs),
    }


def _overlap(left: Iterable[str], right: Iterable[str]) -> list[str]:
    return sorted(set(left) & set(right))


def _near_duplicate_pairs(
    validation: list[dict[str, Any]], holdout: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for left in validation:
        for right in holdout:
            similarity = _question_similarity(left["question"], right["question"])
            if similarity >= NEAR_DUPLICATE_THRESHOLD:
                pairs.append(
                    {
                        "validation_id": left["id"],
                        "holdout_id": right["id"],
                        "similarity": round(similarity, 6),
                    }
                )
    return pairs


def _audit_payload(
    dataset_root: Path,
    records: list[dict[str, Any]],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    by_split = {
        split: [record for record in records if record["split"] == split]
        for split in SPLITS
    }
    invalid_split = [
        record["id"] for record in records if record.get("split") not in SPLITS
    ]
    if invalid_split:
        raise SplitAuditError(f"存在非法 split: {invalid_split}")
    if any(not by_split[split] for split in SPLITS):
        raise SplitAuditError("validation 和 holdout 都必须有记录")

    summaries = {split: _split_summary(by_split[split]) for split in SPLITS}
    validation_summary = summaries["validation"]
    holdout_summary = summaries["holdout"]
    overlaps = {
        "case_ids": _overlap(
            validation_summary["case_ids"], holdout_summary["case_ids"]
        ),
        "fact_family_ids": _overlap(
            validation_summary["fact_family_ids"], holdout_summary["fact_family_ids"]
        ),
        "topic_ids": _overlap(
            validation_summary["topic_ids"], holdout_summary["topic_ids"]
        ),
        "document_ids": _overlap(
            validation_summary["document_ids"], holdout_summary["document_ids"]
        ),
        "chunk_ids": _overlap(
            validation_summary["chunk_ids"], holdout_summary["chunk_ids"]
        ),
        "qrel_pair_ids": _overlap(
            validation_summary["qrel_pair_ids"], holdout_summary["qrel_pair_ids"]
        ),
        "evidence_control_ids": _overlap(
            validation_summary["evidence_control_ids"],
            holdout_summary["evidence_control_ids"],
        ),
        "evidence_quote_hashes": _overlap(
            validation_summary["evidence_quote_hashes"],
            holdout_summary["evidence_quote_hashes"],
        ),
    }
    normalized_questions = {
        split: sorted(
            _normalise_question(record["question"]) for record in by_split[split]
        )
        for split in SPLITS
    }
    overlaps["normalized_questions"] = _overlap(
        normalized_questions["validation"], normalized_questions["holdout"]
    )
    near_duplicates = _near_duplicate_pairs(by_split["validation"], by_split["holdout"])
    exact_question_duplicates = {
        split: len(normalized_questions[split]) - len(set(normalized_questions[split]))
        for split in SPLITS
    }
    source_gold_sha256 = _file_sha256(dataset_root / "gold_dataset.jsonl")
    expected_gold_sha256 = snapshot["fingerprints"]["gold_dataset"]
    if source_gold_sha256 != expected_gold_sha256:
        raise SplitAuditError(
            "gold_dataset.jsonl 与 DS-04 snapshot 指纹不一致，禁止冻结"
        )
    failures = {name: value for name, value in overlaps.items() if value}
    failures["invalid_split"] = invalid_split
    failures["intra_split_duplicate_questions"] = {
        split: count for split, count in exact_question_duplicates.items() if count
    }
    failures["near_duplicate_questions"] = near_duplicates
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "dataset_id": snapshot["dataset_id"],
        "source_gold_dataset_sha256": source_gold_sha256,
        "source_snapshot_dataset_sha256": snapshot["fingerprints"]["dataset_sha256"],
        "algorithm": {
            "version": ALGORITHM_VERSION,
            "question_normalization": "NFKC + casefold + alphanumeric characters",
            "near_duplicate_threshold": NEAR_DUPLICATE_THRESHOLD,
        },
        "splits": summaries,
        "overlap_checks": overlaps,
        "exact_question_duplicates_by_split": exact_question_duplicates,
        "near_duplicate_questions": near_duplicates,
        "leakage_findings": failures,
        "status": "passed" if not any(failures.values()) else "failed",
    }


def _freeze_from_audit(audit: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": audit["dataset_id"],
        "source_gold_dataset_sha256": audit["source_gold_dataset_sha256"],
        "source_snapshot_dataset_sha256": audit["source_snapshot_dataset_sha256"],
        "algorithm": audit["algorithm"],
        "splits": audit["splits"],
        "status": "frozen",
    }
    return {
        **payload,
        "freeze_sha256": canonical_sha256(payload),
    }


def _audit_with_freeze_hash(
    audit: Mapping[str, Any], freeze: Mapping[str, Any]
) -> dict[str, Any]:
    payload = {**audit, "freeze_sha256": freeze["freeze_sha256"]}
    return {
        **payload,
        "audit_sha256": canonical_sha256(payload),
    }


def _write_json(path: Path, value: Mapping[str, Any], *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise FileExistsError(f"DS-05 输出已存在，需显式 --replace: {path}")
    temporary = path.with_name(f".{path.name}.ds05-part")
    temporary.write_bytes(_canonical_json_bytes(value) + b"\n")
    temporary.replace(path)


def render_audit_markdown(audit: Mapping[str, Any]) -> str:
    overlaps = audit["overlap_checks"]
    splits = audit["splits"]
    lines = [
        "# P2 DS-05 Split Isolation And Leakage Audit",
        "",
        f"- Status: `{audit['status']}`",
        f"- Dataset: `{audit['dataset_id']}`",
        f"- Gold SHA-256: `{audit['source_gold_dataset_sha256']}`",
        f"- Freeze SHA-256: `{audit.get('freeze_sha256', 'not-created')}`",
        "",
        "## Frozen Splits",
        "",
        "| Split | Cases | Topics | Fact families | Documents | Chunks | Records SHA-256 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for split in SPLITS:
        summary = splits[split]
        lines.append(
            f"| {split} | {summary['count']} | {len(summary['topic_ids'])} | "
            f"{len(summary['fact_family_ids'])} | {len(summary['document_ids'])} | "
            f"{len(summary['chunk_ids'])} | `{summary['records_sha256']}` |"
        )
    lines.extend(
        [
            "",
            "## Cross-Split Checks",
            "",
            "| Check | Overlap count |",
            "|---|---:|",
        ]
    )
    for name in (
        "case_ids",
        "normalized_questions",
        "fact_family_ids",
        "topic_ids",
        "document_ids",
        "chunk_ids",
        "qrel_pair_ids",
        "evidence_control_ids",
        "evidence_quote_hashes",
    ):
        lines.append(f"| {name} | {len(overlaps[name])} |")
    lines.extend(
        [
            "",
            f"High-confidence near-duplicate threshold: `{audit['algorithm']['near_duplicate_threshold']}`.",
            f"Near-duplicate question pairs: `{len(audit['near_duplicate_questions'])}`.",
            "",
            "No raw question or document text is included in this report. Any non-zero "
            "finding blocks the DS-05 gate and requires review before evaluation.",
            "",
        ]
    )
    return "\n".join(lines)


def audit_representative_splits(
    dataset_root: Path = DEFAULT_OUTPUT_ROOT,
    contract_root: Path = DEFAULT_CONTRACT_ROOT,
) -> dict[str, Any]:
    dataset_root = Path(dataset_root)
    try:
        validation = validate_representative_dataset(
            dataset_root, contract_root, allow_completed_review=True
        )
    except (OSError, RepresentativeDatasetError, TypeError, ValueError) as exc:
        raise SplitAuditError(f"DS-04 gold 校验无法完成: {exc}") from exc
    if not validation["ok"]:
        raise SplitAuditError(f"DS-04 gold 校验失败: {validation['errors']}")
    snapshot = _load_json(dataset_root / "representative_snapshot.json")
    records = _load_jsonl(dataset_root / "gold_dataset.jsonl")
    return _audit_payload(dataset_root, records, snapshot)


def freeze_representative_splits(
    dataset_root: Path = DEFAULT_OUTPUT_ROOT,
    contract_root: Path = DEFAULT_CONTRACT_ROOT,
    *,
    freeze_path: Path = DEFAULT_FREEZE,
    audit_json_path: Path = DEFAULT_AUDIT_JSON,
    audit_markdown_path: Path = DEFAULT_AUDIT_MARKDOWN,
    replace: bool = False,
) -> dict[str, Any]:
    output_paths = [Path(freeze_path), Path(audit_json_path), Path(audit_markdown_path)]
    if not replace:
        existing = [str(path) for path in output_paths if path.exists()]
        if existing:
            raise FileExistsError(
                f"DS-05 输出已存在，需显式 --replace: {', '.join(existing)}"
            )
    audit = audit_representative_splits(dataset_root, contract_root)
    if audit["status"] != "passed":
        raise SplitAuditError(f"DS-05 泄漏审计失败: {audit['leakage_findings']}")
    freeze = _freeze_from_audit(audit)
    final_audit = _audit_with_freeze_hash(audit, freeze)
    _validate_artifact_schema(
        freeze, Path(contract_root), "split-freeze-v1.schema.json"
    )
    _validate_artifact_schema(
        final_audit, Path(contract_root), "split-audit-v1.schema.json"
    )
    _write_json(Path(freeze_path), freeze, replace=replace)
    _write_json(Path(audit_json_path), final_audit, replace=replace)
    markdown = render_audit_markdown(final_audit)
    markdown_path = Path(audit_markdown_path)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    if markdown_path.exists() and not replace:
        raise FileExistsError(f"DS-05 输出已存在，需显式 --replace: {markdown_path}")
    temporary = markdown_path.with_name(f".{markdown_path.name}.ds05-part")
    temporary.write_text(markdown, encoding="utf-8", newline="\n")
    temporary.replace(markdown_path)
    return {"freeze": freeze, "audit": final_audit}


def validate_frozen_representative_splits(
    dataset_root: Path = DEFAULT_OUTPUT_ROOT,
    contract_root: Path = DEFAULT_CONTRACT_ROOT,
    *,
    freeze_path: Path = DEFAULT_FREEZE,
    audit_json_path: Path = DEFAULT_AUDIT_JSON,
    audit_markdown_path: Path = DEFAULT_AUDIT_MARKDOWN,
) -> dict[str, Any]:
    freeze = _load_json(Path(freeze_path))
    stored_audit = _load_json(Path(audit_json_path))
    _validate_artifact_schema(
        freeze, Path(contract_root), "split-freeze-v1.schema.json"
    )
    _validate_artifact_schema(
        stored_audit, Path(contract_root), "split-audit-v1.schema.json"
    )
    current_audit = audit_representative_splits(dataset_root, contract_root)
    expected_freeze = _freeze_from_audit(current_audit)
    expected_audit = _audit_with_freeze_hash(current_audit, expected_freeze)
    errors: list[str] = []
    if freeze != expected_freeze:
        errors.append("split_freeze.json 与当前 gold/split 内容不一致")
    if stored_audit != expected_audit:
        errors.append("DS-05 审计报告与当前 gold/split 内容不一致")
    markdown_path = Path(audit_markdown_path)
    if markdown_path.is_file():
        if markdown_path.read_text(encoding="utf-8") != render_audit_markdown(
            expected_audit
        ):
            errors.append("DS-05 Markdown 报告与机器可读审计不一致")
    return {
        "ok": not errors,
        "errors": errors,
        "status": "passed" if not errors else "failed",
        "freeze_sha256": expected_freeze["freeze_sha256"],
        "audit_sha256": expected_audit["audit_sha256"],
        "splits": expected_freeze["splits"],
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "freeze", "validate"))
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--contract-root", type=Path, default=DEFAULT_CONTRACT_ROOT)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--report-markdown", type=Path, default=DEFAULT_AUDIT_MARKDOWN)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "audit":
            result = audit_representative_splits(args.dataset_root, args.contract_root)
        elif args.command == "freeze":
            result = freeze_representative_splits(
                args.dataset_root,
                args.contract_root,
                freeze_path=args.freeze,
                audit_json_path=args.report_json,
                audit_markdown_path=args.report_markdown,
                replace=args.replace,
            )
        else:
            result = validate_frozen_representative_splits(
                args.dataset_root,
                args.contract_root,
                freeze_path=args.freeze,
                audit_json_path=args.report_json,
                audit_markdown_path=args.report_markdown,
            )
    except (FileNotFoundError, OSError, SplitAuditError, TypeError, ValueError) as exc:
        print(f"DS-05 split audit: ERROR\n- {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", result.get("status") == "passed") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
