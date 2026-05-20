"""
Tests for the WorkflowEngine end-to-end.
"""

import asyncio
import pytest
from pathlib import Path

from agentse.core.event_bus import EventBus, EventType
from agentse.core.memory import MemoryStore
from agentse.core.task import Task, TaskPriority, TaskStatus
from agentse.core.workflow import WorkflowEngine


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStore:
    return MemoryStore(store_path=tmp_path / "wf_mem.json")


@pytest.fixture
def engine(bus, memory) -> WorkflowEngine:
    return WorkflowEngine(bus, memory)


# ------------------------------------------------------------------ #
# Helper stub agent                                                    #
# ------------------------------------------------------------------ #

def _make_stub_agent(bus, memory, role_str: str, fail: bool = False):
    """Return a minimal agent that either succeeds or raises."""
    from agentse.core.agent import Agent, AgentRole

    class StubAgent(Agent):
        async def process(self, task):
            if fail:
                raise RuntimeError("stub failure")
            return {"stub": True, "role": role_str}

    return StubAgent(role=AgentRole(role_str), event_bus=bus, memory=memory)


# ------------------------------------------------------------------ #
# Tests                                                                #
# ------------------------------------------------------------------ #


def test_single_task_completes(bus, memory, engine) -> None:
    agent = _make_stub_agent(bus, memory, "developer")
    engine.register_agent(agent)

    task = Task(title="T", description="D", role="developer")
    summary = asyncio.run(engine.run_sprint("S1", [task]))

    assert summary["completed"] == 1
    assert summary["failed"] == 0
    assert task.status == TaskStatus.COMPLETED


def test_dependency_order_respected(bus, memory, engine) -> None:
    """Task B must run after task A."""
    order: list[str] = []

    from agentse.core.agent import Agent, AgentRole

    class OrderAgent(Agent):
        async def process(self, task):
            order.append(task.title)
            return {"done": True}

    for role in ["planner", "developer"]:
        engine.register_agent(
            OrderAgent(role=AgentRole(role), event_bus=bus, memory=memory)
        )

    task_a = Task(title="A", description="D", role="planner")
    task_b = Task(title="B", description="D", role="developer", depends_on=[task_a.task_id])

    asyncio.run(engine.run_sprint("S", [task_a, task_b]))

    assert order == ["A", "B"]


def test_failing_task_exhausts_retries(bus, memory, engine) -> None:
    agent = _make_stub_agent(bus, memory, "qa", fail=True)
    engine.register_agent(agent)

    task = Task(title="T", description="D", role="qa", max_attempts=2)
    summary = asyncio.run(engine.run_sprint("S", [task]))

    assert summary["failed"] == 1
    assert task.status == TaskStatus.FAILED
    assert task.attempts == 2


def test_cancelled_task_when_dep_fails(bus, memory, engine) -> None:
    """If an upstream task fails, downstream task should be cancelled."""
    engine.register_agent(_make_stub_agent(bus, memory, "planner", fail=True))
    engine.register_agent(_make_stub_agent(bus, memory, "developer"))

    task_a = Task(title="A", description="D", role="planner", max_attempts=1)
    task_b = Task(title="B", description="D", role="developer", depends_on=[task_a.task_id])

    summary = asyncio.run(engine.run_sprint("S", [task_a, task_b]))

    assert task_a.status == TaskStatus.FAILED
    assert task_b.status == TaskStatus.CANCELLED


def test_no_agent_for_role_marks_failed(bus, memory, engine) -> None:
    task = Task(title="T", description="D", role="architect")
    # No architect registered
    summary = asyncio.run(engine.run_sprint("S", [task]))

    assert summary["failed"] == 1


def test_sprint_events_published(bus, memory, engine) -> None:
    engine.register_agent(_make_stub_agent(bus, memory, "developer"))

    task = Task(title="T", description="D", role="developer")
    asyncio.run(engine.run_sprint("S", [task]))

    event_types = {e.event_type for e in bus.history()}
    assert EventType.SPRINT_STARTED in event_types
    assert EventType.SPRINT_COMPLETED in event_types
    assert EventType.RETROSPECTIVE_TRIGGERED in event_types
    assert EventType.TASK_STARTED in event_types
    assert EventType.TASK_COMPLETED in event_types


def test_summary_has_required_keys(bus, memory, engine) -> None:
    engine.register_agent(_make_stub_agent(bus, memory, "developer"))
    task = Task(title="T", description="D", role="developer")
    summary = asyncio.run(engine.run_sprint("My Sprint", [task]))

    for key in ["sprint_id", "sprint_name", "total", "completed", "failed",
                "cancelled", "avg_task_duration_s", "tasks", "agent_metrics"]:
        assert key in summary, f"Missing summary key: {key}"
