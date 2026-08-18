"""Stable fingerprints for evaluation datasets and document fixtures."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 digest of one file's original bytes."""

    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"评估文件不存在: {target}")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_text_bytes(text: str) -> bytes:
    """Encode text after removing a BOM and normalizing line endings."""

    if not isinstance(text, str):
        raise TypeError("text 必须是字符串")
    normalized = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return normalized.encode("utf-8")


def text_sha256(text: str) -> str:
    """Hash logical UTF-8 text independently of BOM and line endings."""

    return hashlib.sha256(_canonical_text_bytes(text)).hexdigest()


def text_file_sha256(path: str | Path) -> str:
    """Hash one UTF-8 text file using the canonical text representation."""

    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"评估文件不存在: {target}")
    try:
        text = target.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"评估文本不是有效 UTF-8: {target}") from exc
    return text_sha256(text)


def text_corpus_sha256(directory: str | Path) -> str:
    """Hash TXT fixture names and canonical UTF-8 text deterministically."""

    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"评估文档目录不存在: {root}")
    paths = sorted(root.glob("*.txt"), key=lambda path: path.name)
    if not paths:
        raise ValueError(f"评估文档目录没有 TXT 文件: {root}")

    digest = hashlib.sha256()
    for path in paths:
        try:
            content = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"评估文本不是有效 UTF-8: {path}") from exc
        for value in (path.name.encode("utf-8"), _canonical_text_bytes(content)):
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)
    return digest.hexdigest()
