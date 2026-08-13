"""Milvus-backed vector storage for the RAG system."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.documents import Document
from pymilvus import DataType, MilvusClient

from app.utils.logger import get_logger

logger = get_logger(__name__)


class VectorStore:
    """Expose the application's vector-store contract on top of Milvus."""

    _CONFIG_ID = "__rag_embedding_space__"
    _RECORD_TYPE_FIELD = "record_type"
    _CHUNK_RECORD_TYPE = "chunk"
    _CONFIG_RECORD_TYPE = "config"
    _IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    _DELETE_BATCH_SIZE = 500
    _QUERY_BATCH_SIZE = 1000
    _ID_MAX_BYTES = 512
    _DOCUMENT_MAX_BYTES = 65535

    def __init__(
        self,
        collection_name: str = "rag_documents",
        uri: str = "http://127.0.0.1:19530",
        token: Optional[str] = None,
        db_name: str = "default",
    ):
        collection_name = collection_name.strip()
        uri = uri.strip()
        db_name = db_name.strip()
        if not collection_name:
            raise ValueError("collection_name cannot be empty")
        if not uri:
            raise ValueError("Milvus URI cannot be empty")
        if not db_name:
            raise ValueError("Milvus database name cannot be empty")

        self.collection_name = collection_name
        self.uri = uri
        self.db_name = db_name
        client_kwargs: Dict[str, Any] = {"uri": uri, "db_name": db_name}
        if token:
            client_kwargs["token"] = token
        self.client = MilvusClient(**client_kwargs)
        self._embedding_dimension: Optional[int] = None
        self._collection_ready = self.client.has_collection(
            collection_name=self.collection_name
        )
        if self._collection_ready:
            self.client.load_collection(collection_name=self.collection_name)
        logger.info(
            "Milvus vector store ready: collection={}, exists={}, uri={}, database={}",
            self.collection_name,
            self._collection_ready,
            self.uri,
            self.db_name,
        )

    @staticmethod
    def _sanitize_metadata(metadata: Dict) -> Dict:
        """Keep JSON-compatible scalar metadata and remove empty values."""
        sanitized: Dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                sanitized[str(key)] = value
            else:
                sanitized[str(key)] = str(value)
        return sanitized

    @staticmethod
    def _fallback_chunk_id(document: Document, index: int) -> str:
        """Generate a deterministic ID for callers that omit chunk_id."""
        source = (
            document.metadata.get("source_file")
            or document.metadata.get("source")
            or "unknown"
        )
        page = document.metadata.get("page_number") or document.metadata.get("page") or ""
        chunk_index = document.metadata.get("chunk_index", index)
        payload = f"{source}\0{page}\0{chunk_index}\0{document.page_content}".encode(
            "utf-8"
        )
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _validate_embeddings(embeddings: List[List[float]]) -> None:
        if not embeddings:
            return
        dimension = len(embeddings[0])
        if dimension == 0:
            raise ValueError("Embedding vector cannot be empty")
        if any(len(embedding) != dimension for embedding in embeddings):
            raise ValueError("Embedding dimensions must match within one batch")

    @staticmethod
    def _utf8_size(value: str) -> int:
        return len(value.encode("utf-8"))

    @classmethod
    def _validate_id(cls, value: Any) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Chunk ID cannot be empty")
        if normalized == cls._CONFIG_ID:
            raise ValueError(f"Chunk ID {normalized!r} is reserved for internal use")
        size = cls._utf8_size(normalized)
        if size > cls._ID_MAX_BYTES:
            raise ValueError(
                f"Chunk ID exceeds Milvus VARCHAR limit: {size} > {cls._ID_MAX_BYTES} UTF-8 bytes"
            )
        return normalized

    @classmethod
    def _validate_document(cls, value: str) -> None:
        if not value.strip():
            raise ValueError("Empty document chunks cannot be written")
        size = cls._utf8_size(value)
        if size > cls._DOCUMENT_MAX_BYTES:
            raise ValueError(
                "Document chunk exceeds Milvus VARCHAR limit: "
                f"{size} > {cls._DOCUMENT_MAX_BYTES} UTF-8 bytes"
            )

    def _require_embedding_dimension(self) -> int:
        if self._embedding_dimension is not None:
            return self._embedding_dimension
        record = self._config_record()
        if record is None or "embedding_dimension" not in record:
            raise RuntimeError(
                "Call ensure_embedding_space before writing or searching vectors"
            )
        try:
            dimension = int(record["embedding_dimension"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Milvus Collection has invalid embedding_dimension metadata"
            ) from exc
        if dimension <= 0:
            raise ValueError("Milvus Collection embedding dimension must be positive")
        self._embedding_dimension = dimension
        return dimension

    def _validate_vector_dimension(self, vector: List[float], *, operation: str) -> None:
        expected = self._require_embedding_dimension()
        actual = len(vector)
        if actual != expected:
            raise ValueError(
                f"{operation} embedding dimension does not match the Milvus Collection: "
                f"{actual} != {expected}"
            )

    @classmethod
    def _literal(cls, value: Any) -> str:
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError("Milvus metadata filters only support scalar values")
        return json.dumps(value, ensure_ascii=False)

    @classmethod
    def _filter_expression(cls, where: Optional[Dict] = None) -> str:
        expressions = [
            f'{cls._RECORD_TYPE_FIELD} == {cls._literal(cls._CHUNK_RECORD_TYPE)}'
        ]
        for key, value in (where or {}).items():
            normalized_key = str(key)
            if not cls._IDENTIFIER_PATTERN.fullmatch(normalized_key):
                raise ValueError(f"Invalid metadata filter field: {normalized_key!r}")
            expressions.append(f"{normalized_key} == {cls._literal(value)}")
        return " and ".join(expressions)

    def _create_collection(
        self,
        provider: str,
        model: str,
        dimension: int,
    ) -> None:
        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=True,
        )
        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=512,
        )
        schema.add_field(
            field_name="vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=dimension,
        )
        schema.add_field(
            field_name="document",
            datatype=DataType.VARCHAR,
            max_length=65535,
        )
        schema.add_field(field_name="metadata", datatype=DataType.JSON)
        schema.add_field(
            field_name=self._RECORD_TYPE_FIELD,
            datatype=DataType.VARCHAR,
            max_length=16,
        )

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="AUTOINDEX",
            metric_type="L2",
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
            consistency_level="Strong",
        )
        self.client.insert(
            collection_name=self.collection_name,
            data=[
                {
                    "id": self._CONFIG_ID,
                    "vector": [0.0] * dimension,
                    "document": "",
                    "metadata": {},
                    self._RECORD_TYPE_FIELD: self._CONFIG_RECORD_TYPE,
                    "embedding_provider": provider,
                    "embedding_model": model,
                    "embedding_dimension": dimension,
                }
            ],
        )
        self._flush()
        self.client.load_collection(collection_name=self.collection_name)
        self._collection_ready = True
        self._embedding_dimension = dimension

    def _flush(self) -> None:
        self.client.flush(collection_name=self.collection_name)

    def _config_record(self) -> Optional[Dict]:
        if not self._collection_ready:
            return None
        rows = self.client.query(
            collection_name=self.collection_name,
            filter=f'id == {self._literal(self._CONFIG_ID)}',
            output_fields=[
                "embedding_provider",
                "embedding_model",
                "embedding_dimension",
            ],
            limit=1,
        )
        return dict(rows[0]) if rows else None

    def _query_all(self, *, filter_expression: str, output_fields: List[str]) -> List[Dict]:
        iterator_factory = getattr(self.client, "query_iterator", None)
        if not callable(iterator_factory):
            return list(
                self.client.query(
                    collection_name=self.collection_name,
                    filter=filter_expression,
                    output_fields=output_fields,
                    limit=16384,
                )
            )

        iterator = iterator_factory(
            collection_name=self.collection_name,
            batch_size=self._QUERY_BATCH_SIZE,
            filter=filter_expression,
            output_fields=output_fields,
        )
        rows: List[Dict] = []
        try:
            while True:
                batch = iterator.next()
                if not batch:
                    break
                rows.extend(batch)
        finally:
            iterator.close()
        return rows

    def ensure_embedding_space(
        self,
        provider: str,
        model: str,
        dimension: int,
    ) -> None:
        """Create or validate the Collection's embedding-space contract."""
        provider = str(provider).strip()
        model = str(model).strip()
        if not provider or not model:
            raise ValueError("Embedding provider and model cannot be empty")
        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive")

        if not self._collection_ready:
            self._create_collection(provider, model, dimension)
            return

        record = self._config_record()
        if record is None:
            raise ValueError(
                "Existing Milvus Collection has no embedding-space metadata; "
                "use a new COLLECTION_NAME and rebuild the index"
            )

        expected = {
            "embedding_provider": provider,
            "embedding_model": model,
            "embedding_dimension": dimension,
        }
        for key, value in expected.items():
            stored = record.get(key)
            if str(stored) != str(value):
                if self.count() == 0:
                    self.delete_collection()
                    self._create_collection(provider, model, dimension)
                    return
                raise ValueError(
                    "Embedding space is incompatible with the existing collection: "
                    f"{key} {value!r} != {stored!r}"
                )
        self._embedding_dimension = dimension

    def add_documents(
        self,
        documents: List[Document],
        embeddings: List[List[float]],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Idempotently write document chunks using their stable IDs."""
        if len(documents) != len(embeddings):
            raise ValueError(
                f"Document count ({len(documents)}) does not match embedding count "
                f"({len(embeddings)})"
            )
        if not documents:
            return []
        self._validate_embeddings(embeddings)
        if not self._collection_ready:
            raise RuntimeError("Call ensure_embedding_space before writing vectors")
        self._validate_vector_dimension(embeddings[0], operation="Document")

        if ids is None:
            ids = [
                str(
                    document.metadata.get("chunk_id")
                    or self._fallback_chunk_id(document, index)
                )
                for index, document in enumerate(documents)
            ]
        if len(ids) != len(documents):
            raise ValueError("ID count must match document count")
        normalized_ids = [self._validate_id(value) for value in ids]
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("Duplicate chunk IDs exist in the same batch")

        rows: List[Dict] = []
        for chunk_id, document, embedding in zip(
            normalized_ids, documents, embeddings
        ):
            self._validate_document(document.page_content)
            metadata = self._sanitize_metadata(document.metadata)
            rows.append(
                {
                    **metadata,
                    "id": chunk_id,
                    "vector": embedding,
                    "document": document.page_content,
                    "metadata": metadata,
                    self._RECORD_TYPE_FIELD: self._CHUNK_RECORD_TYPE,
                }
            )

        try:
            self.client.upsert(collection_name=self.collection_name, data=rows)
            self._flush()
            logger.info(
                "Milvus vector write completed: upserted={}, total={}",
                len(rows),
                self.count(),
            )
            return normalized_ids
        except Exception:
            logger.exception("Milvus vector write failed")
            raise

    def search(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict] = None,
    ) -> Dict:
        """Search with L2 distance and return the existing flattened result contract."""
        if not query_embedding:
            raise ValueError("Query embedding cannot be empty")
        if n_results <= 0:
            raise ValueError("n_results must be positive")
        if not self._collection_ready:
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
        self._validate_vector_dimension(query_embedding, operation="Query")
        chunk_count = self.count()
        if chunk_count == 0:
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}

        try:
            results = self.client.search(
                collection_name=self.collection_name,
                data=[query_embedding],
                anns_field="vector",
                filter=self._filter_expression(where),
                limit=min(n_results, chunk_count),
                output_fields=["document", "metadata"],
                search_params={"metric_type": "L2", "params": {}},
            )
            hits = results[0] if results else []
            entities = [dict(hit.get("entity") or {}) for hit in hits]
            return {
                "ids": [str(hit.get("id")) for hit in hits],
                "documents": [str(entity.get("document") or "") for entity in entities],
                "metadatas": [dict(entity.get("metadata") or {}) for entity in entities],
                "distances": [float(hit.get("distance")) for hit in hits],
            }
        except Exception:
            logger.exception("Milvus vector search failed")
            raise

    def delete_by_ids(self, ids: List[str]) -> None:
        """Delete chunks by primary key."""
        normalized = [
            self._validate_id(value) for value in ids if str(value).strip()
        ]
        if not normalized or not self._collection_ready:
            return
        try:
            for offset in range(0, len(normalized), self._DELETE_BATCH_SIZE):
                self.client.delete(
                    collection_name=self.collection_name,
                    ids=normalized[offset : offset + self._DELETE_BATCH_SIZE],
                )
            self._flush()
            logger.info("Deleted {} document chunks from Milvus", len(normalized))
        except Exception:
            logger.exception("Milvus chunk deletion by ID failed")
            raise

    def _delete_by_filter(self, field_name: str, value: str) -> None:
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
        if not self._collection_ready:
            return
        self.client.delete(
            collection_name=self.collection_name,
            filter=self._filter_expression({field_name: value}),
        )
        self._flush()

    def delete_by_document_id(self, document_id: str) -> None:
        self._delete_by_filter("document_id", document_id)

    def delete_by_index_id(self, index_id: str) -> None:
        self._delete_by_filter("index_id", index_id)

    def count(self) -> int:
        """Return the number of document chunks, excluding the config record."""
        if not self._collection_ready:
            return 0
        rows = self.client.query(
            collection_name=self.collection_name,
            filter=self._filter_expression(),
            output_fields=["count(*)"],
        )
        if not rows:
            return 0
        return int(rows[0].get("count(*)", 0))

    def count_by_index_id(self, index_id: str) -> int:
        if not index_id.strip():
            raise ValueError("index_id cannot be empty")
        if not self._collection_ready:
            return 0
        rows = self.client.query(
            collection_name=self.collection_name,
            filter=self._filter_expression({"index_id": index_id}),
            output_fields=["count(*)"],
        )
        return int(rows[0].get("count(*)", 0)) if rows else 0

    def list_ids_by_index_id(self, index_id: str) -> List[str]:
        if not index_id.strip():
            raise ValueError("index_id cannot be empty")
        if not self._collection_ready:
            return []
        rows = self._query_all(
            filter_expression=self._filter_expression({"index_id": index_id}),
            output_fields=["id"],
        )
        return [str(row["id"]) for row in rows]

    def list_index_ids(self) -> List[str]:
        counts, _ = self.index_inventory()
        return sorted(counts)

    def index_inventory(self) -> tuple[Dict[str, int], int]:
        if not self._collection_ready:
            return {}, 0
        rows = self._query_all(
            filter_expression=self._filter_expression(),
            output_fields=["metadata"],
        )
        counts: Dict[str, int] = {}
        legacy_count = 0
        for row in rows:
            metadata = dict(row.get("metadata") or {})
            index_id = metadata.get("index_id")
            if not index_id:
                legacy_count += 1
                continue
            normalized = str(index_id)
            counts[normalized] = counts.get(normalized, 0) + 1
        return counts, legacy_count

    def count_legacy_chunks(self) -> int:
        _, legacy_count = self.index_inventory()
        return legacy_count

    def close(self) -> None:
        client = getattr(self, "client", None)
        close = getattr(client, "close", None)
        if callable(close):
            close()

    def delete_collection(self) -> None:
        if not self._collection_ready:
            return
        try:
            self.client.drop_collection(collection_name=self.collection_name)
            self._collection_ready = False
            self._embedding_dimension = None
            logger.info("Dropped Milvus Collection: {}", self.collection_name)
        except Exception:
            logger.exception("Dropping Milvus Collection failed")
            raise

    def get_collection_info(self) -> Dict:
        record = self._config_record() or {}
        return {
            "name": self.collection_name,
            "count": self.count(),
            "metadata": {
                key: record[key]
                for key in (
                    "embedding_provider",
                    "embedding_model",
                    "embedding_dimension",
                )
                if key in record
            },
        }

    def peek_documents(self, limit: int = 5) -> Dict:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not self._collection_ready:
            return {"ids": [], "documents": [], "metadatas": []}
        rows = self.client.query(
            collection_name=self.collection_name,
            filter=self._filter_expression(),
            output_fields=["id", "document", "metadata"],
            limit=limit,
        )
        return {
            "ids": [str(row["id"]) for row in rows],
            "documents": [str(row.get("document") or "") for row in rows],
            "metadatas": [dict(row.get("metadata") or {}) for row in rows],
        }
