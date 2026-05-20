"""
Agent base class and role definitions.

Every specialized agent in the engineering team extends this class.
Agents process tasks, emit events, and can store/retrieve knowledge
from the shared MemoryStore.
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from agentse.core.event_bus import EventBus, Event
    from agentse.core.memory import MemoryStore
    from agentse.core.task import Task

logger = structlog.get_logger(__name__)


class AgentRole(str, Enum):
    """Roles available within the engineering team."""

    ORCHESTRATOR = "orchestrator"
    PLANNER = "planner"
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    QA = "qa"
    LEARNER = "learner"


class AgentStatus(str, Enum):
    """Lifecycle status of an agent."""

    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    DONE = "done"
    ERROR = "error"


class AgentMetrics:
    """Lightweight per-agent performance tracker."""

    def __init__(self) -> None:
        self.tasks_completed: int = 0
        self.tasks_failed: int = 0
        self.total_duration_s: float = 0.0
        self.created_at: datetime = datetime.now(timezone.utc)

    def record_success(self, duration_s: float) -> None:
        self.tasks_completed += 1
        self.total_duration_s += duration_s

    def record_failure(self, duration_s: float) -> None:
        self.tasks_failed += 1
        self.total_duration_s += duration_s

    @property
    def avg_duration_s(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return self.total_duration_s / total if total else 0.0

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return self.tasks_completed / total if total else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "avg_duration_s": round(self.avg_duration_s, 3),
            "success_rate": round(self.success_rate, 4),
            "uptime_s": round(
                (datetime.now(timezone.utc) - self.created_at).total_seconds(), 1
            ),
        }


class Agent(ABC):
    """
    Abstract base class for all engineering team agents.

    Subclasses must implement :meth:`process` which receives a :class:`Task`
    and returns a result dict.  The base class handles:
    - Status lifecycle management
    - Event publishing (task_started / task_completed / task_failed)
    - Metrics collection
    - Structured logging
    """

    def __init__(
        self,
        role: AgentRole,
        event_bus: "EventBus",
        memory: "MemoryStore",
        agent_id: str | None = None,
    ) -> None:
        self.agent_id: str = agent_id or str(uuid.uuid4())
        self.role: AgentRole = role
        self.event_bus: "EventBus" = event_bus
        self.memory: "MemoryStore" = memory
        self.status: AgentStatus = AgentStatus.IDLE
        self.metrics: AgentMetrics = AgentMetrics()
        self._log = logger.bind(agent_id=self.agent_id, role=role.value)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, task: "Task") -> dict[str, Any]:
        """
        Execute *task* and return its result.

        Handles the full lifecycle including status updates, timing,
        metric recording, and event publishing.
        """
        from agentse.core.event_bus import Event, EventType

        start = asyncio.get_event_loop().time()
        self.status = AgentStatus.WORKING
        self._log.info("task_started", task_id=task.task_id, title=task.title)

        await self.event_bus.publish(
            Event(
                event_type=EventType.TASK_STARTED,
                source=self.agent_id,
                payload={"task_id": task.task_id, "agent_role": self.role.value},
            )
        )

        try:
            result = await self.process(task)
            duration = asyncio.get_event_loop().time() - start
            self.metrics.record_success(duration)
            self.status = AgentStatus.IDLE
            self._log.info(
                "task_completed",
                task_id=task.task_id,
                duration_s=round(duration, 3),
            )
            await self.event_bus.publish(
                Event(
                    event_type=EventType.TASK_COMPLETED,
                    source=self.agent_id,
                    payload={
                        "task_id": task.task_id,
                        "agent_role": self.role.value,
                        "result": result,
                        "duration_s": round(duration, 3),
                    },
                )
            )
            return result
        except Exception as exc:
            duration = asyncio.get_event_loop().time() - start
            self.metrics.record_failure(duration)
            self.status = AgentStatus.ERROR
            self._log.error(
                "task_failed",
                task_id=task.task_id,
                error=str(exc),
                duration_s=round(duration, 3),
            )
            await self.event_bus.publish(
                Event(
                    event_type=EventType.TASK_FAILED,
                    source=self.agent_id,
                    payload={
                        "task_id": task.task_id,
                        "agent_role": self.role.value,
                        "error": str(exc),
                    },
                )
            )
            raise

    # ------------------------------------------------------------------
    # Abstract interface — subclasses implement this
    # ------------------------------------------------------------------

    @abstractmethod
    async def process(self, task: "Task") -> dict[str, Any]:
        """
        Process *task* and return a result dictionary.

        The returned dict is stored in ``task.result`` by the workflow engine.
        """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """Return a summary of this agent's current state."""
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "status": self.status.value,
            "metrics": self.metrics.to_dict(),
        }
