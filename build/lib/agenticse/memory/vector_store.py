"""In-memory vector store — the episodic / semantic engine (Mem0 analogue).

Implements the "Explicit Experience Library" half of §3.2. Stores lessons,
user preferences and debug golden-rules; supports semantic retrieval with
content-hash deduplication.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from agenticse.memory.embeddings import hash_embedding, hybrid_score
from agenticse.memory.schemas import Lesson, RetrievedMemory


@dataclass
class _VectorRecord:
    record_id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


class InMemoryVectorStore:
    """Pure-Python vector store with content-hash deduplication.

    The interface is intentionally narrow so production deployments can drop
    in Mem0, Milvus, Qdrant, pgvector, etc. by re-implementing the four
    public methods.
    """

    def __init__(self, dim: int = 128) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim
        self._records: Dict[str, _VectorRecord] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def dim(self) -> int:
        return self._dim

    def __len__(self) -> int:
        return len(self._records)

    def upsert(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Iterable[str]] = None,
    ) -> str:
        """Insert ``content`` if its content hash is unseen; return record id."""

        if not content or not content.strip():
            raise ValueError("content must be a non-empty string")
        record_id = _content_hash(content)
        if record_id in self._records:
            existing = self._records[record_id]
            if metadata:
                existing.metadata.update(metadata)
            if tags:
                merged = list(dict.fromkeys([*existing.tags, *tags]))
                existing.tags = merged
            return record_id
        self._records[record_id] = _VectorRecord(
            record_id=record_id,
            content=content,
            embedding=hash_embedding(content, self._dim),
            metadata=dict(metadata or {}),
            tags=list(tags or []),
        )
        return record_id

    def upsert_lesson(self, lesson: Lesson) -> str:
        meta = {
            "lesson_id": lesson.lesson_id,
            "severity": lesson.severity,
            "related_classes": list(lesson.related_classes),
            "timestamp": lesson.timestamp,
        }
        return self.upsert(lesson.content, metadata=meta, tags=lesson.tags)

    def search(
        self,
        query: str,
        top_k: int = 5,
        tag_filter: Optional[Iterable[str]] = None,
        min_score: float = 0.0,
    ) -> List[RetrievedMemory]:
        """Return the top-``k`` semantically similar records."""

        if not query or not query.strip():
            return []
        wanted_tags = set(tag_filter or [])
        results: List[RetrievedMemory] = []
        for rec in self._records.values():
            if wanted_tags and not wanted_tags.intersection(rec.tags):
                continue
            score = hybrid_score(query, rec.content, dim=self._dim)
            if score < min_score:
                continue
            results.append(
                RetrievedMemory(
                    content=rec.content,
                    score=score,
                    source="vector",
                    metadata={
                        "id": rec.record_id,
                        "tags": list(rec.tags),
                        **rec.metadata,
                    },
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[: max(0, top_k)]

    def delete(self, record_id: str) -> bool:
        return self._records.pop(record_id, None) is not None

    def all(self) -> List[RetrievedMemory]:
        return [
            RetrievedMemory(
                content=rec.content,
                score=1.0,
                source="vector",
                metadata={"id": rec.record_id, "tags": list(rec.tags), **rec.metadata},
            )
            for rec in self._records.values()
        ]
