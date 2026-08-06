"""Stable fingerprints for evaluation datasets and document fixtures."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 digest of one file."""

    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"评估文件不存在: {target}")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_corpus_sha256(directory: str | Path) -> str:
    """Hash TXT fixture names and bytes in a deterministic order."""

    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"评估文档目录不存在: {root}")
    paths = sorted(root.glob("*.txt"), key=lambda path: path.name)
    if not paths:
        raise ValueError(f"评估文档目录没有 TXT 文件: {root}")

    digest = hashlib.sha256()
    for path in paths:
        for value in (path.name.encode("utf-8"), path.read_bytes()):
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)
    return digest.hexdigest()
