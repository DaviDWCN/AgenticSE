"""
Tests for MemoryStore.
"""

import pytest
from pathlib import Path


@pytest.fixture
def store(tmp_path: Path):
    from agentse.core.memory import MemoryStore
    return MemoryStore(store_path=tmp_path / "test_memory.json")


def test_short_term_set_get(store) -> None:
    store.set_short("key", "value")
    assert store.get_short("key") == "value"


def test_short_term_default(store) -> None:
    assert store.get_short("missing") is None
    assert store.get_short("missing", 42) == 42


def test_short_term_cleared(store) -> None:
    store.set_short("k", "v")
    store.clear_short_term()
    assert store.get_short("k") is None


def test_long_term_persisted(tmp_path: Path) -> None:
    from agentse.core.memory import MemoryStore

    path = tmp_path / "mem.json"
    s1 = MemoryStore(store_path=path)
    s1.set_long("persistent_key", {"nested": True})

    s2 = MemoryStore(store_path=path)
    assert s2.get_long("persistent_key") == {"nested": True}


def test_long_term_update(store) -> None:
    store.set_long("a", 1)
    store.update_long({"b": 2, "c": 3})
    assert store.get_long("a") == 1
    assert store.get_long("b") == 2
    assert store.get_long("c") == 3


def test_episodic_record_and_query(store) -> None:
    store.record_episode(kind="plan_created", content={"milestone_count": 3}, tags=["planning"])
    store.record_episode(kind="review_completed", content={"verdict": "approved"})
    store.record_episode(kind="plan_created", content={"milestone_count": 4}, tags=["planning"])

    all_eps = store.query_episodes()
    assert len(all_eps) == 3

    plans = store.query_episodes(kind="plan_created")
    assert len(plans) == 2

    tagged = store.query_episodes(tags=["planning"])
    assert len(tagged) == 2


def test_episodic_limit(store) -> None:
    for i in range(10):
        store.record_episode(kind="test_event", content={"i": i})

    result = store.query_episodes(limit=5)
    assert len(result) == 5
    # Should return the last 5
    assert result[-1]["content"]["i"] == 9


def test_memory_summary(store) -> None:
    store.set_short("s1", 1)
    store.set_short("s2", 2)
    store.set_long("l1", "x")
    store.record_episode(kind="evt", content={})

    summary = store.summary()
    assert summary["short_term_keys"] == 2
    assert summary["long_term_keys"] == 1
    assert summary["episodic_count"] == 1
