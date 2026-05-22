import pytest

from agenticse.memory.graph_store import InMemoryGraphStore
from agenticse.memory.schemas import Lesson


def _seed(graph: InMemoryGraphStore) -> None:
    # Class graph: A -> B -> C (depends_on), plus method calls.
    for cls in ("A", "B", "C", "D"):
        graph.upsert_node(cls, "Class")
    graph.upsert_edge("A", "B", "DEPENDS_ON")
    graph.upsert_edge("B", "C", "DEPENDS_ON")
    graph.upsert_edge("D", "A", "DEPENDS_ON")
    graph.upsert_node("A.foo", "Method")
    graph.upsert_node("B.bar", "Method")
    graph.upsert_node("C.baz", "Method")
    graph.upsert_edge("A.foo", "B.bar", "CALLS")
    graph.upsert_edge("B.bar", "C.baz", "CALLS")


def test_strict_mode_rejects_unknown_kinds():
    g = InMemoryGraphStore()
    with pytest.raises(ValueError):
        g.upsert_node("X", "Module")
    g.upsert_node("X", "Class")
    g.upsert_node("Y", "Class")
    with pytest.raises(ValueError):
        g.upsert_edge("X", "Y", "INHERITS")


def test_missing_endpoint_raises():
    g = InMemoryGraphStore()
    g.upsert_node("X", "Class")
    with pytest.raises(KeyError):
        g.upsert_edge("X", "Y", "DEPENDS_ON")


def test_edge_dedupe_updates_properties():
    g = InMemoryGraphStore()
    g.upsert_node("A", "Class")
    g.upsert_node("B", "Class")
    g.upsert_edge("A", "B", "DEPENDS_ON", properties={"weight": 1})
    g.upsert_edge("A", "B", "DEPENDS_ON", properties={"weight": 3})
    assert g.edge_count() == 1
    assert g.all_edges()[0].properties["weight"] == 3


def test_neighbours_upstream_two_downstream_one():
    g = InMemoryGraphStore()
    _seed(g)
    # Anchor on B: upstream depth 2 should find A (1-hop) and D (2-hop via A);
    # downstream depth 1 should find C.
    hits = g.neighbours("B", upstream_depth=2, downstream_depth=1)
    ids = {h.metadata["node_id"] for h in hits}
    assert ids == {"A", "C", "D"}
    directions = {h.metadata["node_id"]: h.metadata["direction"] for h in hits}
    assert directions["A"] == "upstream"
    assert directions["D"] == "upstream"
    assert directions["C"] == "downstream"


def test_neighbours_respects_edge_kind_filter():
    g = InMemoryGraphStore()
    _seed(g)
    hits = g.neighbours("A.foo", downstream_depth=2, upstream_depth=0, edge_kinds=["CALLS"])
    ids = {h.metadata["node_id"] for h in hits}
    assert ids == {"B.bar", "C.baz"}


def test_neighbours_negative_depth_raises():
    g = InMemoryGraphStore()
    g.upsert_node("A", "Class")
    with pytest.raises(ValueError):
        g.neighbours("A", upstream_depth=-1)


def test_attach_lesson_creates_anchor_and_link():
    g = InMemoryGraphStore()
    g.upsert_node("OrderService", "Class")
    lesson = Lesson(
        content="Null-check cart before tax",
        related_classes=["OrderService", "CartService"],
        tags=["bug"],
    )
    g.attach_lesson(lesson, lesson.related_classes)
    # CartService was auto-created.
    assert g.get_node("CartService") is not None
    lessons = g.lessons_for("OrderService")
    assert len(lessons) == 1
    assert "Null-check cart" in lessons[0].content


def test_get_node_missing_returns_none():
    g = InMemoryGraphStore()
    assert g.get_node("nope") is None
    assert g.neighbours("nope") == []
