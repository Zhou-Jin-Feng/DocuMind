"""In-memory MilvusClient test double used by offline unit tests."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


class FakeSchema:
    def __init__(self):
        self.fields: list[dict[str, Any]] = []

    def add_field(self, **kwargs) -> None:
        self.fields.append(dict(kwargs))


class FakeIndexParams:
    def __init__(self):
        self.indexes: list[dict[str, Any]] = []

    def add_index(self, **kwargs) -> None:
        self.indexes.append(dict(kwargs))


class FakeQueryIterator:
    def __init__(self, rows: list[dict], batch_size: int):
        self.rows = rows
        self.batch_size = batch_size
        self.offset = 0

    def next(self) -> list[dict]:
        batch = self.rows[self.offset : self.offset + self.batch_size]
        self.offset += self.batch_size
        return batch

    def close(self) -> None:
        return None


class FakeMilvusClient:
    """Implement the MilvusClient methods exercised by VectorStore."""

    def __init__(self, **kwargs):
        self.connection = dict(kwargs)
        self.collections: dict[str, dict[str, Any]] = {}
        self.closed = False

    @staticmethod
    def create_schema(**kwargs) -> FakeSchema:
        del kwargs
        return FakeSchema()

    @staticmethod
    def prepare_index_params() -> FakeIndexParams:
        return FakeIndexParams()

    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(
        self,
        collection_name: str,
        schema: FakeSchema,
        index_params: FakeIndexParams,
        **kwargs,
    ) -> None:
        self.collections[collection_name] = {
            "schema": schema,
            "index_params": index_params,
            "options": dict(kwargs),
            "rows": {},
        }

    def _rows(self, collection_name: str) -> dict[str, dict]:
        return self.collections[collection_name]["rows"]

    def insert(self, collection_name: str, data) -> None:
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            self._rows(collection_name)[str(row["id"])] = deepcopy(row)

    def upsert(self, collection_name: str, data) -> None:
        self.insert(collection_name, data)

    @staticmethod
    def _matches(row: dict, expression: str) -> bool:
        if not expression:
            return True
        for clause in expression.split(" and "):
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*) == (.+)", clause)
            if match is None:
                raise AssertionError(f"Unsupported fake Milvus filter: {clause}")
            field_name, literal = match.groups()
            if row.get(field_name) != json.loads(literal):
                return False
        return True

    @staticmethod
    def _project(row: dict, output_fields: list[str]) -> dict:
        return {
            field_name: deepcopy(row[field_name])
            for field_name in output_fields
            if field_name in row
        }

    def query(
        self,
        collection_name: str,
        filter: str = "",
        output_fields: list[str] | None = None,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict]:
        del kwargs
        rows = [
            row
            for row in self._rows(collection_name).values()
            if self._matches(row, filter)
        ]
        if output_fields == ["count(*)"]:
            return [{"count(*)": len(rows)}]
        if limit is not None:
            rows = rows[:limit]
        return [self._project(row, output_fields or []) for row in rows]

    def query_iterator(
        self,
        collection_name: str,
        batch_size: int,
        filter: str,
        output_fields: list[str],
        **kwargs,
    ) -> FakeQueryIterator:
        del kwargs
        rows = self.query(
            collection_name=collection_name,
            filter=filter,
            output_fields=output_fields,
        )
        return FakeQueryIterator(rows, batch_size)

    def search(
        self,
        collection_name: str,
        data: list[list[float]],
        filter: str,
        limit: int,
        output_fields: list[str],
        **kwargs,
    ) -> list[list[dict]]:
        del kwargs
        query_vector = data[0]
        candidates = [
            row
            for row in self._rows(collection_name).values()
            if self._matches(row, filter)
        ]
        hits = []
        for row in candidates:
            if len(query_vector) != len(row["vector"]):
                raise ValueError("Vector dimension mismatch")
            distance = sum(
                (left - right) ** 2
                for left, right in zip(query_vector, row["vector"])
            )
            hits.append(
                {
                    "id": row["id"],
                    "distance": distance,
                    "entity": self._project(row, output_fields),
                }
            )
        hits.sort(key=lambda item: item["distance"])
        return [hits[:limit]]

    def delete(
        self,
        collection_name: str,
        ids: list[str] | None = None,
        filter: str | None = None,
        **kwargs,
    ) -> None:
        del kwargs
        rows = self._rows(collection_name)
        if ids is not None:
            for value in ids:
                rows.pop(str(value), None)
            return
        for row_id in [
            row_id
            for row_id, row in rows.items()
            if self._matches(row, filter or "")
        ]:
            rows.pop(row_id, None)

    def flush(self, collection_name: str, **kwargs) -> None:
        del collection_name, kwargs

    def load_collection(self, collection_name: str, **kwargs) -> None:
        del collection_name, kwargs

    def drop_collection(self, collection_name: str) -> None:
        self.collections.pop(collection_name, None)

    def close(self) -> None:
        self.closed = True
