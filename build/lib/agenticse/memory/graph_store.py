"""In-memory Code Property Graph store — the topology engine (Neo4j analogue).

Implements §3.2's "Implicit Topology Library". Models the core schema from
the spec:

* Nodes:  ``Class`` / ``Method`` / ``Field`` / ``Lesson``
* Edges:  ``CALLS`` (method→method), ``DEPENDS_ON`` (class→class),
          ``LESSON_FOR_CLASS`` (lesson→class)

The store supports the bounded-depth neighbourhood query that the awakening
workflow needs ("upstream 2 hops + downstream 1 hop") without requiring a
real graph database.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from agenticse.memory.schemas import Lesson, RetrievedMemory

NodeKind = str  # "Class" | "Method" | "Field" | "Lesson"
RelKind = str  # "CALLS" | "DEPENDS_ON" | "LESSON_FOR_CLASS" | ...


@dataclass
class GraphNode:
    node_id: str
    kind: NodeKind
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: RelKind
    properties: Dict[str, Any] = field(default_factory=dict)


class InMemoryGraphStore:
    """A tiny labelled property graph with bounded-depth traversal."""

    _ALLOWED_NODE_KINDS = {"Class", "Method", "Field", "Lesson"}
    _ALLOWED_REL_KINDS = {
        "CALLS",
        "DEPENDS_ON",
        "LESSON_FOR_CLASS",
        "DEFINES",
        "HAS_FIELD",
    }

    def __init__(self, strict: bool = True) -> None:
        self._strict = strict
        self._nodes: Dict[str, GraphNode] = {}
        # adjacency: source -> list[(edge_kind, target)]
        self._out: Dict[str, List[Tuple[RelKind, str]]] = defaultdict(list)
        self._in: Dict[str, List[Tuple[RelKind, str]]] = defaultdict(list)
        self._edges: List[GraphEdge] = []

    # ------------------------------------------------------------------ #
    # Mutators
    # ------------------------------------------------------------------ #
    def upsert_node(
        self,
        node_id: str,
        kind: NodeKind,
        properties: Optional[Dict[str, Any]] = None,
    ) -> GraphNode:
        if self._strict and kind not in self._ALLOWED_NODE_KINDS:
            raise ValueError(
                f"node kind {kind!r} not in {sorted(self._ALLOWED_NODE_KINDS)}"
            )
        existing = self._nodes.get(node_id)
        if existing is None:
            existing = GraphNode(node_id=node_id, kind=kind, properties=dict(properties or {}))
            self._nodes[node_id] = existing
        else:
            if existing.kind != kind:
                raise ValueError(
                    f"node {node_id!r} already exists as kind {existing.kind!r}"
                )
            if properties:
                existing.properties.update(properties)
        return existing

    def upsert_edge(
        self,
        source: str,
        target: str,
        kind: RelKind,
        properties: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        if self._strict and kind not in self._ALLOWED_REL_KINDS:
            raise ValueError(
                f"relationship kind {kind!r} not in {sorted(self._ALLOWED_REL_KINDS)}"
            )
        if source not in self._nodes:
            raise KeyError(f"source node {source!r} does not exist")
        if target not in self._nodes:
            raise KeyError(f"target node {target!r} does not exist")
        # Deduplicate by (source, target, kind).
        for e in self._edges:
            if e.source == source and e.target == target and e.kind == kind:
                if properties:
                    e.properties.update(properties)
                return e
        edge = GraphEdge(source=source, target=target, kind=kind, properties=dict(properties or {}))
        self._edges.append(edge)
        self._out[source].append((kind, target))
        self._in[target].append((kind, source))
        return edge

    def attach_lesson(
        self,
        lesson: Lesson,
        class_node_ids: Iterable[str],
    ) -> str:
        """Insert ``lesson`` as a ``Lesson`` node and link it to source classes."""

        self.upsert_node(
            lesson.lesson_id,
            "Lesson",
            properties={
                "content": lesson.content,
                "severity": lesson.severity,
                "tags": list(lesson.tags),
                "timestamp": lesson.timestamp,
            },
        )
        for cls in class_node_ids:
            if cls not in self._nodes:
                # Auto-create the missing class anchor — common during reflection.
                self.upsert_node(cls, "Class")
            self.upsert_edge(lesson.lesson_id, cls, "LESSON_FOR_CLASS")
        return lesson.lesson_id

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def neighbours(
        self,
        node_id: str,
        upstream_depth: int = 2,
        downstream_depth: int = 1,
        edge_kinds: Optional[Iterable[RelKind]] = None,
    ) -> List[RetrievedMemory]:
        """Return upstream callers/dependants and downstream callees/dependencies.

        Mirrors §4.1: "upstream 2 hops + downstream 1 hop". The returned
        :class:`RetrievedMemory` objects carry a human-readable path that can
        be inlined into the awakening prompt.
        """

        if node_id not in self._nodes:
            return []
        if upstream_depth < 0 or downstream_depth < 0:
            raise ValueError("depths must be non-negative")
        allowed = set(edge_kinds) if edge_kinds else None

        hits: Dict[str, RetrievedMemory] = {}

        def _walk(start: str, depth: int, forward: bool) -> None:
            if depth == 0:
                return
            adj = self._out if forward else self._in
            queue: deque[Tuple[str, int, List[str]]] = deque([(start, 0, [start])])
            visited: Set[str] = {start}
            while queue:
                cur, d, path = queue.popleft()
                if d >= depth:
                    continue
                for kind, nbr in adj.get(cur, []):
                    if allowed and kind not in allowed:
                        continue
                    if nbr in visited:
                        continue
                    visited.add(nbr)
                    new_path = path + [f"-[{kind}]->" if forward else f"<-[{kind}]-", nbr]
                    direction = "upstream" if not forward else "downstream"
                    rendered = " ".join(new_path)
                    hits[nbr] = RetrievedMemory(
                        content=f"{direction}: {rendered}",
                        score=1.0 / (d + 1),
                        source="graph",
                        metadata={
                            "node_id": nbr,
                            "kind": self._nodes[nbr].kind,
                            "depth": d + 1,
                            "direction": direction,
                        },
                    )
                    queue.append((nbr, d + 1, new_path))

        _walk(node_id, downstream_depth, forward=True)
        _walk(node_id, upstream_depth, forward=False)

        return sorted(hits.values(), key=lambda r: r.score, reverse=True)

    def lessons_for(self, class_node_id: str) -> List[RetrievedMemory]:
        """Return all lessons anchored to ``class_node_id``."""

        out: List[RetrievedMemory] = []
        for kind, src in self._in.get(class_node_id, []):
            if kind != "LESSON_FOR_CLASS":
                continue
            node = self._nodes[src]
            out.append(
                RetrievedMemory(
                    content=node.properties.get("content", ""),
                    score=1.0,
                    source="graph",
                    metadata={
                        "lesson_id": src,
                        "severity": node.properties.get("severity"),
                        "tags": node.properties.get("tags", []),
                    },
                )
            )
        return out

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)

    def all_nodes(self) -> List[GraphNode]:
        return list(self._nodes.values())

    def all_edges(self) -> List[GraphEdge]:
        return list(self._edges)
