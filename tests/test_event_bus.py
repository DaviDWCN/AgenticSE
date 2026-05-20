"""
Tests for the EventBus.
"""

import asyncio
import pytest

from agentse.core.event_bus import Event, EventBus, EventType


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def test_event_bus_subscribe_and_publish(bus: EventBus) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.TASK_COMPLETED, handler)

    event = Event(
        event_type=EventType.TASK_COMPLETED,
        source="test",
        payload={"task_id": "abc"},
    )
    asyncio.run(bus.publish(event))

    assert len(received) == 1
    assert received[0].event_type == EventType.TASK_COMPLETED
    assert received[0].payload["task_id"] == "abc"


def test_event_bus_subscribe_all(bus: EventBus) -> None:
    received: list[Event] = []

    async def global_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe_all(global_handler)

    for et in [EventType.TASK_STARTED, EventType.SPRINT_STARTED, EventType.HEARTBEAT]:
        asyncio.run(bus.publish(Event(event_type=et, source="test")))

    assert len(received) == 3


def test_event_bus_unsubscribe(bus: EventBus) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.TASK_CREATED, handler)
    bus.unsubscribe(EventType.TASK_CREATED, handler)

    asyncio.run(
        bus.publish(Event(event_type=EventType.TASK_CREATED, source="test"))
    )

    assert len(received) == 0


def test_event_bus_history(bus: EventBus) -> None:
    for _ in range(3):
        asyncio.run(
            bus.publish(Event(event_type=EventType.HEARTBEAT, source="test"))
        )
    asyncio.run(
        bus.publish(Event(event_type=EventType.TASK_COMPLETED, source="test"))
    )

    assert len(bus.history()) == 4
    assert len(bus.history(EventType.HEARTBEAT)) == 3
    assert len(bus.history(EventType.TASK_COMPLETED)) == 1


def test_event_bus_stats(bus: EventBus) -> None:
    asyncio.run(bus.publish(Event(event_type=EventType.HEARTBEAT, source="x")))
    asyncio.run(bus.publish(Event(event_type=EventType.HEARTBEAT, source="x")))
    asyncio.run(bus.publish(Event(event_type=EventType.TASK_FAILED, source="x")))

    stats = bus.stats()
    assert stats[EventType.HEARTBEAT.value] == 2
    assert stats[EventType.TASK_FAILED.value] == 1


def test_handler_exception_does_not_abort_delivery(bus: EventBus) -> None:
    """A failing handler must not prevent other handlers from running."""
    received: list[Event] = []

    async def bad_handler(event: Event) -> None:
        raise RuntimeError("boom")

    async def good_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.HEARTBEAT, bad_handler)
    bus.subscribe(EventType.HEARTBEAT, good_handler)

    asyncio.run(bus.publish(Event(event_type=EventType.HEARTBEAT, source="test")))

    # good_handler must still have been called
    assert len(received) == 1


def test_event_to_dict() -> None:
    event = Event(
        event_type=EventType.TASK_STARTED,
        source="agent-1",
        payload={"task_id": "t1"},
        correlation_id="corr-abc",
    )
    d = event.to_dict()
    assert d["event_type"] == "task.started"
    assert d["source"] == "agent-1"
    assert d["payload"]["task_id"] == "t1"
    assert d["correlation_id"] == "corr-abc"
    assert "timestamp" in d
