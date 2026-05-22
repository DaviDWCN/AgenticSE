import pytest

from agenticse.memory import AgentMemorySubsystem
from agenticse.memory.schemas import Lesson, Resolution, SensoryEvent


def test_full_lifecycle():
    ams = AgentMemorySubsystem(token_budget=4_000)

    # Seed prior knowledge.
    ams.record_lesson(
        Lesson(
            content="When CheckoutService fails, first inspect CartService.compute()",
            related_classes=["CheckoutService"],
            tags=["debug"],
        )
    )
    ams.record_dependency("CheckoutService", "CartService")

    # Start a new task.
    ams.start_task(
        "There is a bug in CheckoutService that breaks the cart total",
        active_files=["app/CheckoutService.java"],
    )

    # Awaken from LTM and verify the prompt includes both halves.
    prompt = ams.awaken_prompt()
    assert "Lessons learned" in prompt
    assert "topology" in prompt.lower()
    assert "CartService" in prompt

    # Stream a couple of sensory events.
    n = ams.ingest(
        [
            SensoryEvent(source="terminal", payload="NPE at line 88", kind="stack_trace"),
            SensoryEvent(source="metrics", payload="ignore-me"),  # filtered out
            SensoryEvent(source="ide", payload="patch applied", kind="ast_change"),
        ]
    )
    assert n == 2
    assert any("NPE" in s for s in ams.state.memory_segments.high_res)

    # Finish task, persist a lesson, and verify it now exists in the LTM.
    stored = ams.finish_task(
        [Lesson(content="Always validate cart != null", related_classes=["CartService"])]
    )
    assert len(stored) == 1
    hits = ams.ltm.vector.search("validate cart null")
    assert hits
    # After finishing, no controller is active.
    with pytest.raises(RuntimeError):
        _ = ams.controller


def test_remember_writes_to_chosen_resolution():
    ams = AgentMemorySubsystem()
    ams.start_task("noop")
    ams.remember("structural sig", Resolution.MID)
    assert "structural sig" in ams.state.memory_segments.mid_res


def test_awaken_uses_explicit_anchors_when_given():
    ams = AgentMemorySubsystem()
    ams.record_dependency("Foo", "Bar")
    ams.start_task("free text without symbols")
    ctx = ams.awaken(explicit_anchors=["Foo"])
    ids = {m.metadata.get("node_id") for m in ctx.topology}
    assert "Bar" in ids


def test_finish_without_start_is_safe():
    ams = AgentMemorySubsystem()
    assert ams.finish_task() == []
