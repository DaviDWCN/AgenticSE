"""Snapshot persistence for the Agent Memory Subsystem.

The in-memory stores are ideal for tests and embedders, but coding agents need
a durable hand-off between CLI invocations and editor sessions. This module
serialises the long-term memory matrix plus the optional active working-memory
session into a versioned JSON document.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

try:  # pragma: no cover - exercised only on platforms without fcntl
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

from agenticse.memory.long_term import LongTermMemoryMatrix
from agenticse.memory.schemas import WorkingMemoryState, state_from_dict


SNAPSHOT_VERSION = 1
DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0


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
    """Write ``snapshot`` to ``path`` as UTF-8 JSON.

    Writes are atomic: the JSON is first written and validated in a temporary
    file, the previous snapshot is copied to ``*.bak`` if present, and then the
    temporary file replaces the target path.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_json() + "\n"
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    AgentMemorySnapshot.from_json(tmp_path.read_text(encoding="utf-8"))
    if path.exists():
        shutil.copy2(path, backup_path(path))
    os.replace(str(tmp_path), str(path))


def load_snapshot(path: Path) -> AgentMemorySnapshot:
    """Load a snapshot from ``path``."""

    return AgentMemorySnapshot.from_json(path.read_text(encoding="utf-8"))


def backup_path(path: Path) -> Path:
    """Return the backup path used for ``path``."""

    return path.with_name(f"{path.name}.bak")


def _lock_timeout_error(lock_path: Path, timeout_seconds: float) -> TimeoutError:
    metadata = ""
    try:
        metadata = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    details = f" Lock metadata: {metadata}." if metadata else ""
    return TimeoutError(
        f"Timed out waiting {timeout_seconds:.2f}s for snapshot lock: {lock_path}."
        f"{details} Another agenticse process may be writing the snapshot; "
        "retry or increase --lock-timeout."
    )


def _write_lock_metadata(lock_file: Any) -> None:
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"pid={os.getpid()} acquired_at={time.time():.6f}\n")
    lock_file.flush()


@contextmanager
def snapshot_lock(
    path: Path,
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Hold an exclusive lock for a snapshot read-modify-write cycle."""

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be non-negative")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    if fcntl is None:
        deadline = time.time() + timeout_seconds
        acquired = False
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
                    _write_lock_metadata(lock_file)
                acquired = True
                break
            except FileExistsError:
                if time.time() >= deadline:
                    raise _lock_timeout_error(lock_path, timeout_seconds)
                time.sleep(0.05)
        try:
            yield
        finally:
            if acquired:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
        return

    with lock_path.open("a", encoding="utf-8") as lock_file:
        deadline = time.time() + timeout_seconds
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                _write_lock_metadata(lock_file)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise _lock_timeout_error(lock_path, timeout_seconds)
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)