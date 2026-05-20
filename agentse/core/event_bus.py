"""
Async in-process event bus.

Agents communicate exclusively through events — no direct method calls
between agents.  This decoupling allows the workflow engine to be
replaced with an external broker (e.g. Redis Streams, NATS) without
touching agent logic.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger(__name__)


class EventType(str, Enum):
    """All events that can flow through the team's event bus."""

    # Task lifecycle
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_BLOCKED = "task.blocked"
    TASK_RETRIED = "task.retried"

    # Sprint / workflow level
    SPRINT_STARTED = "sprint.started"
    SPRINT_COMPLETED = "sprint.completed"

    # Learning & improvement
    RETROSPECTIVE_TRIGGERED = "retrospective.triggered"
    PROCESS_IMPROVED = "process.improved"
    KNOWLEDGE_UPDATED = "knowledge.updated"

    # Sandbox
    SANDBOX_RESULT = "sandbox.result"

    # Generic
    AGENT_REGISTERED = "agent.registered"
    HEARTBEAT = "heartbeat"


Handler = Callable[["Event"], Coroutine[Any, Any, None]]


class Event:
    """An immutable event travelling through the bus."""

    def __init__(
        self,
        event_type: EventType,
        source: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.event_id: str = str(uuid.uuid4())
        self.event_type: EventType = event_type
        self.source: str = source
        self.payload: dict[str, Any] = payload or {}
        self.correlation_id: str = correlation_id or self.event_id
        self.timestamp: datetime = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<Event type={self.event_type.value} "
            f"source={self.source} id={self.event_id[:8]}>"
        )


class EventBus:
    """
    Async publish-subscribe event bus.

    Handlers are registered per :class:`EventType` and called concurrently
    when a matching event is published.  Wildcard subscription is supported
    via ``subscribe_all``.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = {
            et: [] for et in EventType
        }
        self._global_handlers: list[Handler] = []
        self._history: list[Event] = []
        self._log = logger.bind(component="event_bus")

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """Register *handler* for a specific *event_type*."""
        self._handlers[event_type].append(handler)
        self._log.debug("handler_registered", event_type=event_type.value)

    def subscribe_all(self, handler: Handler) -> None:
        """Register *handler* for every event type."""
        self._global_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        """Remove a previously registered handler."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: Event) -> None:
        """
        Publish *event* to all registered handlers.

        All handlers are awaited concurrently with ``asyncio.gather``.
        Individual handler failures are logged but do not abort delivery
        to other handlers.
        """
        self._history.append(event)
        self._log.debug(
            "event_published",
            event_type=event.event_type.value,
            source=event.source,
            event_id=event.event_id[:8],
        )

        handlers = self._handlers[event.event_type] + self._global_handlers
        if not handlers:
            return

        results = await asyncio.gather(
            *[h(event) for h in handlers], return_exceptions=True
        )
        for h, result in zip(handlers, results):
            if isinstance(result, Exception):
                self._log.error(
                    "handler_error",
                    handler=getattr(h, "__name__", repr(h)),
                    error=str(result),
                )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def history(self, event_type: EventType | None = None) -> list[Event]:
        """Return event history, optionally filtered by type."""
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if e.event_type == event_type]

    def clear_history(self) -> None:
        self._history.clear()

    def stats(self) -> dict[str, int]:
        """Return a count per event type."""
        counts: dict[str, int] = {}
        for event in self._history:
            counts[event.event_type.value] = (
                counts.get(event.event_type.value, 0) + 1
            )
        return counts
