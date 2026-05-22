"""Snapshot persistence for the Agent Memory Subsystem.

The in-memory stores are ideal for tests and embedders, but coding agents need
a durable hand-off between CLI invocations and editor sessions. This module
serialises the long-term memory matrix plus the optional active working-memory
session into a versioned JSON document.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from agenticse.memory.long_term import LongTermMemoryMatrix
from agenticse.memory.schemas import WorkingMemoryState, state_from_dict


SNAPSHOT_VERSION = 1


@dataclass
class AgentMemorySnapshot:
    """Versioned snapshot of LTM and the optional active task state."""

    version: int = SNAPSHOT_VERSION
    created_at: float = field(default_factory=time.time)
    long_term: LongTermMemoryMatrix = field(default_factory=LongTermMemoryMatrix)
    working_state: Optional[WorkingMemoryState] = None
    last_task_input: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "long_term": self.long_term.to_dict(),
            "working_state": (
                self.working_state.to_dict() if self.working_state is not None else None
            ),
            "last_task_input": self.last_task_input,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMemorySnapshot":
        version = int(data.get("version", SNAPSHOT_VERSION))
        if version != SNAPSHOT_VERSION:
            raise ValueError(f"Unsupported snapshot version: {version}")
        raw_state = data.get("working_state")
        return cls(
            version=version,
            created_at=float(data.get("created_at", time.time())),
            long_term=LongTermMemoryMatrix.from_dict(data.get("long_term", {})),
            working_state=state_from_dict(raw_state) if raw_state else None,
            last_task_input=str(data.get("last_task_input", "")),
        )

    @classmethod
    def from_json(cls, text: str) -> "AgentMemorySnapshot":
        return cls.from_dict(json.loads(text))


def snapshot_ltm(ltm: LongTermMemoryMatrix) -> AgentMemorySnapshot:
    """Capture only the long-term memory matrix."""

    return AgentMemorySnapshot(long_term=LongTermMemoryMatrix.from_dict(ltm.to_dict()))


def restore_ltm(snapshot: AgentMemorySnapshot) -> LongTermMemoryMatrix:
    """Return the long-term memory matrix held by ``snapshot``."""

    return snapshot.long_term


def snapshot_ams(ams: Any) -> AgentMemorySnapshot:
    """Capture an ``AgentMemorySubsystem`` without importing its class eagerly."""

    controller = getattr(ams, "_controller", None)
    return AgentMemorySnapshot(
        long_term=LongTermMemoryMatrix.from_dict(ams.ltm.to_dict()),
        working_state=(
            state_from_dict(controller.state.to_dict()) if controller is not None else None
        ),
        last_task_input=getattr(ams, "_last_task_input", ""),
    )


def restore_ams(snapshot: AgentMemorySnapshot) -> Any:
    """Restore an ``AgentMemorySubsystem`` from a snapshot."""

    from agenticse.memory.ams import AgentMemorySubsystem
    from agenticse.memory.working import WorkingMemoryController

    ams = AgentMemorySubsystem(long_term=snapshot.long_term)
    if snapshot.working_state is not None:
        ams._controller = WorkingMemoryController(state=snapshot.working_state)
        ams._last_task_input = snapshot.last_task_input
    return ams


def save_snapshot(snapshot: AgentMemorySnapshot, path: Path) -> None:
    """Write ``snapshot`` to ``path`` as UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot.to_json() + "\n", encoding="utf-8")


def load_snapshot(path: Path) -> AgentMemorySnapshot:
    """Load a snapshot from ``path``."""

    return AgentMemorySnapshot.from_json(path.read_text(encoding="utf-8"))