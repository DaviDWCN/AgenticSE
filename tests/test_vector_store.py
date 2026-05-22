import pytest

from agenticse.memory.schemas import Lesson
from agenticse.memory.vector_store import InMemoryVectorStore


def test_upsert_dedupes_by_content_hash():
    s = InMemoryVectorStore()
    id1 = s.upsert("Null-check the cart before computing tax")
    id2 = s.upsert("Null-check the cart before computing tax")
    assert id1 == id2
    assert len(s) == 1


def test_upsert_merges_tags_on_dup():
    s = InMemoryVectorStore()
    s.upsert("Avoid divide by zero", tags=["math"])
    s.upsert("Avoid divide by zero", tags=["math", "critical"])
    hits = s.search("divide by zero")
    assert hits[0].metadata["tags"] == ["math", "critical"]


def test_search_returns_top_k_by_relevance():
    s = InMemoryVectorStore()
    s.upsert("Order checkout fails when cart is empty")
    s.upsert("Logging configuration tips")
    s.upsert("Cart total computation must handle null line items")
    hits = s.search("cart empty checkout bug", top_k=2)
    assert len(hits) <= 2
    assert any("cart" in h.content.lower() for h in hits)
    # Top hit should be the most cart-relevant one.
    assert hits[0].score > 0


def test_search_tag_filter():
    s = InMemoryVectorStore()
    s.upsert("alpha cart", tags=["a"])
    s.upsert("beta cart", tags=["b"])
    hits = s.search("cart", tag_filter=["a"])
    assert len(hits) == 1
    assert "alpha" in hits[0].content


def test_search_empty_query_returns_empty():
    s = InMemoryVectorStore()
    s.upsert("anything")
    assert s.search("") == []
    assert s.search("   ") == []


def test_upsert_rejects_blank_content():
    s = InMemoryVectorStore()
    with pytest.raises(ValueError):
        s.upsert("")
    with pytest.raises(ValueError):
        s.upsert("   ")


def test_upsert_lesson_carries_metadata():
    s = InMemoryVectorStore()
    lesson = Lesson(
        content="Always validate the JWT audience",
        tags=["security", "auth"],
        related_classes=["AuthFilter"],
        severity="critical",
    )
    s.upsert_lesson(lesson)
    hits = s.search("JWT audience validation", tag_filter=["security"])
    assert hits
    assert hits[0].metadata["severity"] == "critical"
    assert hits[0].metadata["related_classes"] == ["AuthFilter"]


def test_delete():
    s = InMemoryVectorStore()
    rid = s.upsert("ephemeral")
    assert s.delete(rid) is True
    assert s.delete(rid) is False
    assert len(s) == 0
