"""
Workflow engine — the heartbeat of the autonomous engineering team.

Responsibilities
----------------
- Maintain a registry of agents.
- Accept task graphs (lists of :class:`~agentse.core.task.Task` objects with
  dependency edges).
- Resolve dependency order and dispatch tasks to the correct agent as soon as
  all upstream tasks are satisfied.
- Retry failed tasks up to their ``max_attempts`` limit.
- Emit a RETROSPECTIVE_TRIGGERED event at the end of each sprint so the
  self-learning engine can analyse what happened and improve the process.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from agentse.core.agent import Agent, AgentRole
from agentse.core.event_bus import Event, EventBus, EventType
from agentse.core.task import Task, TaskStatus

logger = structlog.get_logger(__name__)


class WorkflowEngine:
    """
    Async workflow engine coordinating the full engineering team.

    Usage
    -----
    ::

        engine = WorkflowEngine(event_bus, memory)
        engine.register_agent(orchestrator)
        engine.register_agent(developer)
        results = await engine.run_sprint("Sprint 1", tasks)
    """

    def __init__(self, event_bus: EventBus, memory: Any) -> None:
        self.event_bus: EventBus = event_bus
        self.memory: Any = memory
        self._agents: dict[AgentRole, Agent] = {}
        self._log = logger.bind(component="workflow_engine")

    # ------------------------------------------------------------------
    # Agent registry
    # ------------------------------------------------------------------

    def register_agent(self, agent: Agent) -> None:
        """Register an agent for a role.  One agent per role for now."""
        self._agents[agent.role] = agent
        self._log.info("agent_registered", role=agent.role.value, id=agent.agent_id[:8])

    def get_agent(self, role: AgentRole) -> Agent | None:
        return self._agents.get(role)

    # ------------------------------------------------------------------
    # Sprint execution
    # ------------------------------------------------------------------

    async def run_sprint(
        self,
        sprint_name: str,
        tasks: list[Task],
        concurrency: int = 4,
    ) -> dict[str, Any]:
        """
        Execute all *tasks* for a named sprint.

        Tasks are dispatched in dependency order with up to *concurrency*
        tasks running simultaneously.  Returns a sprint summary dict.
        """
        sprint_id = f"sprint_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        for task in tasks:
            task.sprint_id = sprint_id

        self._log.info(
            "sprint_started",
            sprint=sprint_name,
            sprint_id=sprint_id,
            task_count=len(tasks),
        )
        await self.event_bus.publish(
            Event(
                event_type=EventType.SPRINT_STARTED,
                source="workflow_engine",
                payload={"sprint_id": sprint_id, "sprint_name": sprint_name},
            )
        )

        task_map: dict[str, Task] = {t.task_id: t for t in tasks}
        completed_ids: set[str] = set()
        failed_ids: set[str] = set()

        semaphore = asyncio.Semaphore(concurrency)

        async def _run_one(task: Task) -> None:
            async with semaphore:
                try:
                    role = AgentRole(task.role)
                except ValueError:
                    role = None  # unknown role string

                agent = self._agents.get(role) if role is not None else None
                if agent is None:
                    self._log.error(
                        "no_agent_for_role", role=task.role, task_id=task.task_id
                    )
                    # Mark permanently failed — no retry makes sense without an agent
                    task.attempts = task.max_attempts  # exhaust retries
                    task.mark_failed(f"No agent registered for role '{task.role}'")
                    failed_ids.add(task.task_id)
                    return

                task.mark_started()
                try:
                    result = await agent.run(task)
                    task.mark_completed(result)
                    completed_ids.add(task.task_id)
                except Exception as exc:
                    task.mark_failed(str(exc))
                    if task.status == TaskStatus.FAILED:
                        failed_ids.add(task.task_id)

        pending = list(tasks)
        in_flight: set[str] = set()

        while pending or in_flight:
            # Dispatch all newly-ready tasks
            to_dispatch = [
                t
                for t in pending
                if t.task_id not in in_flight
                and t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                and t.is_ready(completed_ids)
            ]
            for task in to_dispatch:
                in_flight.add(task.task_id)
                pending.remove(task)

            if to_dispatch:
                coros = [_run_one(t) for t in to_dispatch]
                await asyncio.gather(*coros)
                # After gather, update in_flight
                for t in to_dispatch:
                    in_flight.discard(t.task_id)
                    # Re-queue tasks that failed but can still retry
                    if (
                        t.status == TaskStatus.PENDING
                        and t.attempts < t.max_attempts
                    ):
                        pending.append(t)
            else:
                # Nothing dispatchable — avoid busy-loop
                await asyncio.sleep(0)
                # Detect deadlock: pending tasks whose deps will never complete
                blocked = [
                    t
                    for t in pending
                    if any(dep in failed_ids for dep in t.depends_on)
                ]
                for t in blocked:
                    t.status = TaskStatus.CANCELLED
                    t.error = "Upstream dependency failed"
                    failed_ids.add(t.task_id)
                    pending.remove(t)
                if not blocked:
                    break

        summary = self._build_summary(sprint_name, sprint_id, tasks)
        self._log.info(
            "sprint_completed",
            sprint=sprint_name,
            completed=summary["completed"],
            failed=summary["failed"],
        )

        # Persist sprint record
        self.memory.record_episode(
            kind="sprint_completed",
            content=summary,
            tags=["sprint", sprint_id],
        )

        await self.event_bus.publish(
            Event(
                event_type=EventType.SPRINT_COMPLETED,
                source="workflow_engine",
                payload=summary,
            )
        )

        # Trigger the learning engine
        await self.event_bus.publish(
            Event(
                event_type=EventType.RETROSPECTIVE_TRIGGERED,
                source="workflow_engine",
                payload={"sprint_id": sprint_id, "summary": summary},
            )
        )

        return summary

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_summary(
        self, sprint_name: str, sprint_id: str, tasks: list[Task]
    ) -> dict[str, Any]:
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        failed = [t for t in tasks if t.status == TaskStatus.FAILED]
        cancelled = [t for t in tasks if t.status == TaskStatus.CANCELLED]
        durations = [t.duration_s for t in completed if t.duration_s is not None]

        return {
            "sprint_id": sprint_id,
            "sprint_name": sprint_name,
            "total": len(tasks),
            "completed": len(completed),
            "failed": len(failed),
            "cancelled": len(cancelled),
            "avg_task_duration_s": (
                round(sum(durations) / len(durations), 3) if durations else 0.0
            ),
            "tasks": [t.to_dict() for t in tasks],
            "agent_metrics": {
                role.value: agent.metrics.to_dict()
                for role, agent in self._agents.items()
            },
        }
