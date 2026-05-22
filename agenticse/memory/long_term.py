"""Long-term memory matrix — composes the vector + graph engines (§3.2)."""

from __future__ import annotations

from typing import Iterable, List, Optional

from agenticse.memory.graph_store import InMemoryGraphStore
from agenticse.memory.schemas import AwakeningContext, Lesson, RetrievedMemory
from agenticse.memory.vector_store import InMemoryVectorStore


class LongTermMemoryMatrix:
    """Dual-engine LTM that unifies semantic lessons and code topology."""

    def __init__(
        self,
        vector_store: Optional[InMemoryVectorStore] = None,
        graph_store: Optional[InMemoryGraphStore] = None,
    ) -> None:
        self.vector = vector_store or InMemoryVectorStore()
        self.graph = graph_store or InMemoryGraphStore()

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def record_lesson(self, lesson: Lesson) -> str:
        """Persist a lesson to *both* engines and link it to its source classes."""

        self.vector.upsert_lesson(lesson)
        if lesson.related_classes:
            self.graph.attach_lesson(lesson, lesson.related_classes)
        return lesson.lesson_id

    def record_call(self, caller: str, callee: str) -> None:
        self.graph.upsert_node(caller, "Method")
        self.graph.upsert_node(callee, "Method")
        self.graph.upsert_edge(caller, callee, "CALLS")

    def record_dependency(self, source_class: str, target_class: str) -> None:
        self.graph.upsert_node(source_class, "Class")
        self.graph.upsert_node(target_class, "Class")
        self.graph.upsert_edge(source_class, target_class, "DEPENDS_ON")

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def search_lessons(
        self,
        query: str,
        top_k: int = 5,
        tags: Optional[Iterable[str]] = None,
    ) -> List[RetrievedMemory]:
        return self.vector.search(query, top_k=top_k, tag_filter=tags)

    def topology_around(
        self,
        anchor: str,
        upstream_depth: int = 2,
        downstream_depth: int = 1,
    ) -> List[RetrievedMemory]:
        return self.graph.neighbours(
            anchor, upstream_depth=upstream_depth, downstream_depth=downstream_depth
        )

    def awaken(
        self,
        query: str,
        anchors: Iterable[str] = (),
        top_k_lessons: int = 5,
        upstream_depth: int = 2,
        downstream_depth: int = 1,
    ) -> AwakeningContext:
        """Run §4.1's parallel awakening: vector search + topology expansion."""

        lessons = self.search_lessons(query, top_k=top_k_lessons)
        topology: List[RetrievedMemory] = []
        seen: set[str] = set()
        for anchor in anchors:
            for hit in self.topology_around(anchor, upstream_depth, downstream_depth):
                node_id = hit.metadata.get("node_id")
                key = f"{node_id}:{hit.metadata.get('direction')}"
                if key in seen:
                    continue
                seen.add(key)
                topology.append(hit)
        return AwakeningContext(lessons=lessons, topology=topology)
