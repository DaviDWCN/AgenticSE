from agenticse.memory.long_term import LongTermMemoryMatrix
from agenticse.memory.schemas import Lesson, SensoryEvent, WorkingMemoryState
from agenticse.memory.working import WorkingMemoryController
from agenticse.memory.workflows import (
    PerceptionPolicy,
    awaken_for_task,
    consolidate_session,
    extract_anchors,
    ingest_events,
    perception_filter,
)


def test_perception_filter_drops_noise_and_unknown_sources():
    events = [
        SensoryEvent(source="ide", payload="real change"),
        SensoryEvent(source="metrics", payload="cpu=0.5"),  # unknown source
        SensoryEvent(source="terminal", payload="DEBUG heartbeat tick"),  # noise
        SensoryEvent(source="user", payload=""),  # empty
        SensoryEvent(source="user", payload="please fix the bug"),
    ]
    kept = perception_filter(events)
    assert [e.payload for e in kept] == ["real change", "please fix the bug"]


def test_ingest_events_returns_kept_count_and_writes_state():
    c = WorkingMemoryController()
    n = ingest_events(
        c,
        [
            SensoryEvent(source="terminal", payload="stack frame", kind="stack_trace"),
            SensoryEvent(source="bogus", payload="ignored"),
        ],
    )
    assert n == 1
    assert any("stack frame" in s for s in c.segments.high_res)


def test_extract_anchors_finds_paths_and_class_names():
    text = "Fix NullPointerException in app/services/OrderService.java when CheckoutFlow runs"
    anchors = extract_anchors(text)
    assert "app/services/OrderService.java" in anchors
    assert "NullPointerException" in anchors
    assert "OrderService" in anchors
    assert "CheckoutFlow" in anchors


def test_awaken_returns_lessons_and_topology():
    ltm = LongTermMemoryMatrix()
    ltm.record_lesson(
        Lesson(
            content="Always null-check the cart before computing checkout total",
            related_classes=["OrderService"],
            tags=["bug", "checkout"],
        )
    )
    ltm.record_dependency("OrderService", "CartService")
    ltm.record_dependency("CheckoutController", "OrderService")
    ctx = awaken_for_task(
        "Fix NPE in OrderService when cart is empty",
        ltm,
    )
    assert ctx.lessons, "expected at least one lesson"
    assert any("OrderService" in m.content or m.metadata.get("node_id") == "OrderService"
               or m.metadata.get("node_id") in {"CartService", "CheckoutController"}
               for m in ctx.topology)
    rendered = ctx.render_prompt()
    assert "Lessons learned" in rendered
    assert "topology" in rendered.lower()


def test_awaken_with_explicit_anchors_overrides_extraction():
    ltm = LongTermMemoryMatrix()
    ltm.record_dependency("X", "Y")
    ctx = awaken_for_task("plain text without class names", ltm, explicit_anchors=["X"])
    ids = {m.metadata.get("node_id") for m in ctx.topology}
    assert "Y" in ids


def test_consolidate_persists_lessons_and_trajectory():
    state = WorkingMemoryState()
    state.memory_segments.low_res = ["[abstract] Step 1: applied patch v1"]
    ltm = LongTermMemoryMatrix()
    stored = consolidate_session(
        state,
        ltm,
        [Lesson(content="Validate input length", related_classes=["Parser"])],
    )
    assert len(stored) == 1
    # Lesson + trajectory both in vector store.
    assert len(ltm.vector) == 2
    traj_hits = ltm.vector.search("patch v1", tag_filter=["trajectory"])
    assert traj_hits
    # Lesson got anchored in graph too.
    assert ltm.graph.get_node("Parser") is not None


def test_perception_policy_custom_overrides():
    pol = PerceptionPolicy(allowed_sources={"sensor"}, noisy_substrings={"X"})
    events = [
        SensoryEvent(source="sensor", payload="hello"),
        SensoryEvent(source="sensor", payload="contains X noise"),
        SensoryEvent(source="ide", payload="ignored"),
    ]
    assert [e.payload for e in perception_filter(events, pol)] == ["hello"]


def test_perception_policy_defaults_are_independent():
    first = PerceptionPolicy()
    second = PerceptionPolicy()

    first.allowed_sources.add("sensor")

    assert "sensor" in first.allowed_sources
    assert "sensor" not in second.allowed_sources
