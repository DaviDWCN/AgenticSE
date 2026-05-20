"""
Task model — the unit of work passed between agents.

Tasks form a DAG: each task may depend on upstream tasks (``depends_on``).
The workflow engine resolves these dependencies before dispatching.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"       # dependencies satisfied, eligible for dispatch
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class Task:
    """
    A unit of work assigned to a specific :class:`~agentse.core.agent.AgentRole`.

    Attributes
    ----------
    task_id:      Unique identifier.
    title:        Short human-readable summary.
    description:  Full task description / prompt for the agent.
    role:         Which agent role should handle this task.
    priority:     Scheduling priority.
    depends_on:   task_ids that must complete before this task is READY.
    context:      Arbitrary extra data passed to the agent.
    result:       Output populated by the agent after completion.
    attempts:     How many times execution has been attempted.
    max_attempts: Maximum retries before the task is marked FAILED.
    """

    def __init__(
        self,
        title: str,
        description: str,
        role: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        depends_on: list[str] | None = None,
        context: dict[str, Any] | None = None,
        task_id: str | None = None,
        max_attempts: int = 3,
        sprint_id: str | None = None,
    ) -> None:
        self.task_id: str = task_id or str(uuid.uuid4())
        self.title: str = title
        self.description: str = description
        self.role: str = role
        self.priority: TaskPriority = priority
        self.depends_on: list[str] = depends_on or []
        self.context: dict[str, Any] = context or {}
        self.result: dict[str, Any] = {}
        self.status: TaskStatus = TaskStatus.PENDING
        self.attempts: int = 0
        self.max_attempts: int = max_attempts
        self.sprint_id: str | None = sprint_id
        self.created_at: datetime = datetime.now(timezone.utc)
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.error: str | None = None

    # ------------------------------------------------------------------

    def mark_started(self) -> None:
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)
        self.attempts += 1

    def mark_completed(self, result: dict[str, Any]) -> None:
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str) -> None:
        self.error = error
        if self.attempts >= self.max_attempts:
            self.status = TaskStatus.FAILED
        else:
            self.status = TaskStatus.PENDING  # eligible for retry

    def is_ready(self, completed_ids: set[str]) -> bool:
        """Return True if all upstream dependencies are completed."""
        return all(dep in completed_ids for dep in self.depends_on)

    @property
    def duration_s(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "role": self.role,
            "priority": self.priority.value,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "sprint_id": self.sprint_id,
            "context": self.context,
            "result": self.result,
            "error": self.error,
            "duration_s": self.duration_s,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }

    def __repr__(self) -> str:
        return (
            f"<Task id={self.task_id[:8]} role={self.role} "
            f"status={self.status.value} title={self.title!r}>"
        )
