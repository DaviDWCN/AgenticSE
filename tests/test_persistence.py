from pathlib import Path

import pytest

from agenticse.memory import AgentMemorySubsystem, LongTermMemoryMatrix
from agenticse.memory.persistence import (
    AgentMemorySnapshot,
    backup_path,
    load_snapshot,
    restore_ltm,
    save_snapshot,
    snapshot_ltm,
)
from agenticse.memory.schemas import Lesson, SensoryEvent


def test_ltm_snapshot_round_trip_preserves_lessons_and_topology():
    ltm = LongTermMemoryMatrix()
    ltm.record_lesson(
        Lesson(
            content="Null-check cart before computing tax",
            tags=["checkout"],
            related_classes=["CartService"],
            severity="critical",
        )
    )
    ltm.record_dependency("CheckoutService", "CartService")

    restored = restore_ltm(AgentMemorySnapshot.from_json(snapshot_ltm(ltm).to_json()))

    hits = restored.search_lessons("cart tax", tags=["checkout"])
    assert hits
    assert hits[0].metadata["severity"] == "critical"
    neighbours = restored.topology_around("CheckoutService")
    assert {item.metadata["node_id"] for item in neighbours} == {"CartService"}


def test_ams_snapshot_preserves_active_working_state():
    ams = AgentMemorySubsystem(token_budget=4_000)
    ams.start_task("Fix CheckoutService", active_files=["app/CheckoutService.java"])
    ams.ingest(
        [SensoryEvent(source="terminal", payload="NPE at line 88", kind="stack_trace")]
    )

    restored = AgentMemorySubsystem.from_snapshot(
        AgentMemorySnapshot.from_json(ams.snapshot().to_json())
    )

    assert restored.state.active_file_focus == ["app/CheckoutService.java"]
    assert "NPE at line 88" in restored.controller.render_context()
    assert restored.awaken_prompt() == ""


def test_save_and_load_snapshot_file(tmp_path: Path):
    path = tmp_path / "state.json"
    ams = AgentMemorySubsystem()
    ams.record_lesson(Lesson(content="Prefer bounded graph walks", tags=["graph"]))

    save_snapshot(ams.snapshot(), path)
    restored = AgentMemorySubsystem.from_snapshot(load_snapshot(path))

    assert restored.ltm.search_lessons("bounded graph", tags=["graph"])


def test_save_snapshot_writes_backup_on_second_save(tmp_path: Path):
    path = tmp_path / "state.json"
    first = AgentMemorySubsystem()
    first.record_lesson(Lesson(content="First snapshot"))
    second = AgentMemorySubsystem()
    second.record_lesson(Lesson(content="Second snapshot"))

    save_snapshot(first.snapshot(), path)
    save_snapshot(second.snapshot(), path)

    backup = AgentMemorySubsystem.from_snapshot(load_snapshot(backup_path(path)))
    current = AgentMemorySubsystem.from_snapshot(load_snapshot(path))
    assert backup.ltm.search_lessons("First snapshot")
    assert current.ltm.search_lessons("Second snapshot")


def test_snapshot_is_not_mutated_by_later_ams_changes():
    ams = AgentMemorySubsystem()
    ams.record_lesson(Lesson(content="Original lesson"))

    snapshot = ams.snapshot()
    ams.record_lesson(Lesson(content="Later lesson"))

    restored = AgentMemorySubsystem.from_snapshot(snapshot)
    assert restored.ltm.search_lessons("Original lesson")
    assert not restored.ltm.vector.search("Later lesson", min_score=0.99)


def test_snapshot_rejects_unknown_version():
    with pytest.raises(ValueError):
        AgentMemorySnapshot.from_dict({"version": 999})