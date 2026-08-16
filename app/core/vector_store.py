"""Milvus 向量存储适配器及 Embedding 空间一致性约束。"""

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
    """
    在 Milvus 之上实现应用需要的写入、检索和生命周期操作。

    Collection 内除业务 Chunk 外还保存一条配置记录，用于锁定 Provider、
    模型和维度。所有业务查询都会按 ``record_type`` 排除该记录，避免把配置
    哨兵当成知识片段返回。
    """

    _CONFIG_ID = "__rag_embedding_space__"
    _RECORD_TYPE_FIELD = "record_type"
    _CHUNK_RECORD_TYPE = "chunk"
    _CONFIG_RECORD_TYPE = "config"
    _IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    _DELETE_BATCH_SIZE = 500
    _QUERY_BATCH_SIZE = 1000
    # Milvus 的 VARCHAR 上限按 UTF-8 字节计算，不等同于 Python 字符数。
    _ID_MAX_BYTES = 512
    _DOCUMENT_MAX_BYTES = 65535

    def __init__(
        self,
        collection_name: str = "rag_documents",
        uri: str = "http://127.0.0.1:19530",
        token: Optional[str] = None,
        db_name: str = "default",
    ):
        """连接 Milvus；已有 Collection 会立即加载，配置稍后由调用方校验。"""
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
        """将元数据收敛为可同时写入 JSON 字段和动态字段的标量值。"""
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
        """
        为缺少 ``chunk_id`` 的调用方生成确定性 ID。

        NUL 分隔来源、页码、块序号和正文，避免普通字符串拼接产生边界歧义；
        相同输入会得到相同主键，因此重试会走 Upsert 而不是重复插入。
        """
        source = (
            document.metadata.get("source_file")
            or document.metadata.get("source")
            or "unknown"
        )
        page = (
            document.metadata.get("page_number") or document.metadata.get("page") or ""
        )
        chunk_index = document.metadata.get("chunk_index", index)
        payload = f"{source}\0{page}\0{chunk_index}\0{document.page_content}".encode(
            "utf-8"
        )
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _validate_embeddings(embeddings: List[List[float]]) -> None:
        """拒绝空向量或批次内维度不一致的向量。"""
        if not embeddings:
            return
        dimension = len(embeddings[0])
        if dimension == 0:
            raise ValueError("Embedding vector cannot be empty")
        if any(len(embedding) != dimension for embedding in embeddings):
            raise ValueError("Embedding dimensions must match within one batch")

    @staticmethod
    def _utf8_size(value: str) -> int:
        """返回字符串实际写入 Milvus VARCHAR 时占用的字节数。"""
        return len(value.encode("utf-8"))

    @classmethod
    def _validate_id(cls, value: Any) -> str:
        """规范化 Chunk ID，并保护内部配置主键和 Milvus 字节上限。"""
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
        """在发起 RPC 前拒绝空正文和超过 VARCHAR 上限的 Chunk。"""
        if not value.strip():
            raise ValueError("Empty document chunks cannot be written")
        size = cls._utf8_size(value)
        if size > cls._DOCUMENT_MAX_BYTES:
            raise ValueError(
                "Document chunk exceeds Milvus VARCHAR limit: "
                f"{size} > {cls._DOCUMENT_MAX_BYTES} UTF-8 bytes"
            )

    def _require_embedding_dimension(self) -> int:
        """从缓存或配置记录读取维度；未建立空间契约时拒绝读写。"""
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

    def _validate_vector_dimension(
        self, vector: List[float], *, operation: str
    ) -> None:
        """确保写入或查询向量与 Collection 的 Embedding 空间一致。"""
        expected = self._require_embedding_dimension()
        actual = len(vector)
        if actual != expected:
            raise ValueError(
                f"{operation} embedding dimension does not match the Milvus Collection: "
                f"{actual} != {expected}"
            )

    @classmethod
    def _literal(cls, value: Any) -> str:
        """用 JSON 编码过滤值，避免手工拼接字符串转义。"""
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError("Milvus metadata filters only support scalar values")
        return json.dumps(value, ensure_ascii=False)

    @classmethod
    def _filter_expression(cls, where: Optional[Dict] = None) -> str:
        """
        构建只匹配业务 Chunk 的 Milvus 表达式。

        值由 JSON 负责编码，字段名则必须符合标识符白名单；两者共同避免
        元数据过滤条件改变表达式结构。
        """
        expressions = [
            f"{cls._RECORD_TYPE_FIELD} == {cls._literal(cls._CHUNK_RECORD_TYPE)}"
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
        """
        创建 Collection，并写入定义 Embedding 空间的配置记录。

        动态字段用于服务端元数据过滤，JSON 字段用于完整返回元数据。配置
        记录必须提供占位向量以满足同一 Schema，但会被 ``record_type`` 隔离。
        """
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
            # 生命周期服务在写入后立即核对计数，需要读到刚完成的 Upsert。
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
        """同步刷新当前 Collection。"""
        self.client.flush(collection_name=self.collection_name)

    def _config_record(self) -> Optional[Dict]:
        """读取内部空间配置；Collection 或配置不存在时返回 ``None``。"""
        if not self._collection_ready:
            return None
        rows = self.client.query(
            collection_name=self.collection_name,
            filter=f"id == {self._literal(self._CONFIG_ID)}",
            output_fields=[
                "embedding_provider",
                "embedding_model",
                "embedding_dimension",
            ],
            limit=1,
        )
        return dict(rows[0]) if rows else None

    def _query_all(
        self, *, filter_expression: str, output_fields: List[str]
    ) -> List[Dict]:
        """
        查询全部匹配记录，并兼容没有 ``query_iterator`` 的旧客户端。

        迭代器无论成功或异常都会关闭；兼容路径受 Milvus 单次 16384 条上限
        约束，只用于旧客户端。
        """
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
        """
        建立或验证 Collection 的 Embedding 空间契约。

        空 Collection 可以按新配置重建；非空 Collection 一旦 Provider、模型
        或维度不匹配就拒绝继续，防止不同向量空间的数据被混合检索。
        """
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
        """
        用稳定主键 Upsert 文档块，并返回最终采用的主键。

        元数据既展开为动态字段以支持 Milvus 过滤，也保留 JSON 副本以便
        查询时完整还原；同一批次出现重复主键会直接失败。
        """
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
        for chunk_id, document, embedding in zip(normalized_ids, documents, embeddings):
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
        """
        执行 L2 向量搜索，距离越小表示越相关。

        返回值继续采用旧 Chroma 适配层的扁平字典契约，避免检索层感知底层
        数据库迁移；内部配置记录始终由过滤表达式排除。
        """
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
                "metadatas": [
                    dict(entity.get("metadata") or {}) for entity in entities
                ],
                "distances": [float(hit.get("distance")) for hit in hits],
            }
        except Exception:
            logger.exception("Milvus vector search failed")
            raise

    def delete_by_ids(self, ids: List[str]) -> None:
        """按主键分批删除 Chunk，避免构造过大的单次 RPC。"""
        normalized = [self._validate_id(value) for value in ids if str(value).strip()]
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
        """按受控元数据字段删除全部匹配 Chunk。"""
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
        """按 ``document_id`` 删除所有关联 Chunk。"""
        self._delete_by_filter("document_id", document_id)

    def delete_by_index_id(self, index_id: str) -> None:
        """按 ``index_id`` 删除所有关联 Chunk。"""
        self._delete_by_filter("index_id", index_id)

    def count(self) -> int:
        """统计业务 Chunk 数量，不包含内部配置记录。"""
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
        """统计指定 ``index_id`` 的 Chunk 数量。"""
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
        """列出指定 ``index_id`` 的全部 Chunk ID。"""
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
        """列出排序后的全部 ``index_id``。"""
        counts, _ = self.index_inventory()
        return sorted(counts)

    def index_inventory(self) -> tuple[Dict[str, int], int]:
        """
        返回各 ``index_id`` 的 Chunk 数量和无法归属索引的旧数据数量。

        旧数据指迁移前没有 ``metadata.index_id`` 的 Chunk，单独计数可以让
        生命周期盘点明确暴露待重建数据，而不是静默忽略。
        """
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
        """统计缺少 ``index_id`` 的旧版 Chunk。"""
        _, legacy_count = self.index_inventory()
        return legacy_count

    def close(self) -> None:
        """关闭 Milvus 客户端；兼容没有 ``close`` 的测试替身。"""
        client = getattr(self, "client", None)
        close = getattr(client, "close", None)
        if callable(close):
            close()

    def delete_collection(self) -> None:
        """不可逆地删除整个 Collection，并清空本地空间状态。"""
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
        """返回 Collection 名称、业务 Chunk 数量和 Embedding 空间元数据。"""
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
        """返回少量业务 Chunk，供调试和人工检查使用。"""
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
