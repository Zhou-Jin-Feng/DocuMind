"""Command line operations for the synchronous document lifecycle."""

from __future__ import annotations

import argparse
import json
import sys
from types import SimpleNamespace
from typing import Any, Sequence

from app.config import settings
from app.core.document_chunker import DocumentChunker
from app.core.document_loader import UniversalDocumentLoader
from app.core.embedding_client import UniversalEmbeddingClient
from app.core.vector_store import VectorStore
from app.lifecycle.models import IndexAuditReport, RebuildPlan
from app.lifecycle.registry import DocumentRegistry
from app.lifecycle.service import DocumentLifecycleService


def _build_service(
    *,
    with_embedding: bool,
    with_manifest: bool = False,
) -> DocumentLifecycleService:
    if with_embedding and with_manifest:
        raise ValueError("Embedding client and static manifest are mutually exclusive")
    provider = settings.default_embedding_provider
    if with_embedding:
        embedding_client = UniversalEmbeddingClient(provider)
    elif with_manifest:
        embedding_client = SimpleNamespace(
            provider=provider,
            config=UniversalEmbeddingClient.configuration_for(provider),
            manifest_only=True,
        )
    else:
        embedding_client = None
    return DocumentLifecycleService(
        loader=UniversalDocumentLoader(),
        chunker=DocumentChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        ),
        embedding_client=embedding_client,
        vector_store=VectorStore(
            collection_name=settings.collection_name,
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            db_name=settings.milvus_db_name,
        ),
        registry=DocumentRegistry(settings.document_registry_path),
        upload_dir=settings.upload_dir,
        tenant_id=settings.default_tenant_id,
        collection_id=settings.collection_name,
    )


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"Object is not JSON serializable: {type(value).__name__}")


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=_json_default))


def _print_audit(report: IndexAuditReport, *, as_json: bool) -> None:
    if as_json:
        _print_json(report)
        return
    print(f"healthy: {'yes' if report.healthy else 'no'}")
    print(f"active: {len(report.active_index_ids)}")
    print(f"stale: {len(report.stale_index_ids)}")
    print(f"orphans: {len(report.orphan_index_ids)}")
    print(f"missing_active: {len(report.missing_active_index_ids)}")
    print(f"mismatched_active: {len(report.mismatched_active_index_ids)}")
    print(f"legacy_chunks: {report.legacy_chunk_count}")
    for label, values in (
        ("stale_ids", report.stale_index_ids),
        ("orphan_ids", report.orphan_index_ids),
        ("missing_active_ids", report.missing_active_index_ids),
        ("mismatched_active_ids", report.mismatched_active_index_ids),
    ):
        if values:
            print(f"{label}: {', '.join(values)}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.lifecycle",
        description="Inspect and operate the local document/index lifecycle.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list", help="List registered documents and indexes"
    )
    list_parser.add_argument("--json", action="store_true", help="Emit JSON")

    audit_parser = subparsers.add_parser(
        "audit", help="Audit registry and Milvus state"
    )
    audit_parser.add_argument("--json", action="store_true", help="Emit JSON")

    cleanup_parser = subparsers.add_parser(
        "cleanup", help="Delete stale or orphaned chunks"
    )
    cleanup_parser.add_argument("--include-orphans", action="store_true")
    cleanup_parser.add_argument("--dry-run", action="store_true")
    cleanup_parser.add_argument("--json", action="store_true", help="Emit JSON")

    rebuild_parser = subparsers.add_parser(
        "rebuild", help="Rebuild one or all active documents"
    )
    target = rebuild_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--document-key")
    target.add_argument("--all", action="store_true", dest="all_documents")
    rebuild_parser.add_argument("--dry-run", action="store_true")
    rebuild_parser.add_argument(
        "--retry",
        action="store_true",
        help="Release an interrupted active build before rebuilding",
    )
    rebuild_parser.add_argument("--json", action="store_true", help="Emit JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    service: DocumentLifecycleService | None = None
    try:
        if args.command == "list":
            service = _build_service(with_embedding=False)
            documents = service.registry.list_documents(
                tenant_id=service.tenant_id,
                collection_id=service.collection_id,
            )
            indexes = service.registry.list_indexes(
                tenant_id=service.tenant_id,
                collection_id=service.collection_id,
            )
            payload = {
                "documents": documents,
                "indexes": indexes,
                "vector_count": service.vector_store.count(),
            }
            if args.json:
                _print_json(payload)
            else:
                for document in documents:
                    print(
                        f"{document['display_name']} "
                        f"document_key={document['document_key']} "
                        f"active_index_id={document['active_index_id'] or '-'}"
                    )
                print(f"documents: {len(documents)}")
                print(f"indexes: {len(indexes)}")
                print(f"vectors: {payload['vector_count']}")
            return 0

        if args.command == "audit":
            service = _build_service(with_embedding=False)
            report = service.audit()
            _print_audit(report, as_json=args.json)
            return 0 if report.healthy else 2

        if args.command == "cleanup":
            service = _build_service(with_embedding=False)
            report = service.cleanup(
                include_orphans=args.include_orphans,
                dry_run=args.dry_run,
            )
            _print_audit(report, as_json=args.json)
            return 0

        if args.command == "rebuild":
            service = _build_service(
                with_embedding=not args.dry_run,
                with_manifest=args.dry_run,
            )
            documents = service.registry.list_documents(
                tenant_id=service.tenant_id,
                collection_id=service.collection_id,
            )
            keys = (
                [str(document["document_key"]) for document in documents]
                if args.all_documents
                else [str(args.document_key)]
            )
            results: list[dict[str, Any]] = []
            failed = False
            for document_key in keys:
                try:
                    result = service.rebuild_document(
                        document_key,
                        dry_run=args.dry_run,
                        retry=args.retry,
                    )
                    results.append(result.to_dict())
                except Exception as exc:
                    failed = True
                    results.append(
                        {
                            "status": "error",
                            "document_key": document_key,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
            if args.json:
                _print_json(results)
            else:
                for result in results:
                    print(
                        f"{result['document_key']}: "
                        f"{result['status']}"
                        + (
                            f" ({result.get('error_type')})"
                            if "error_type" in result
                            else ""
                        )
                    )
            return 1 if failed else 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if service is not None:
            close = getattr(service, "close", None)
            if callable(close):
                close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
