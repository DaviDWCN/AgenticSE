"""
OrchestratorAgent — the project manager / team lead.

Responsibilities
----------------
- Receive a high-level engineering goal.
- Break it into a *sprint plan*: an ordered list of :class:`~agentse.core.task.Task`
  objects assigned to the right specialist agents.
- Re-plan if the workflow engine reports failures.
- Apply lessons learned from the MemoryStore to improve sprint planning over time.

In a production system the ``process`` method would call an LLM with the
requirement description + team capabilities.  Here we provide a concrete
implementation that generates a canonical task graph for any software
feature request.
"""

from __future__ import annotations

from typing import Any

import structlog

from agentse.core.agent import Agent, AgentRole
from agentse.core.event_bus import EventBus
from agentse.core.memory import MemoryStore
from agentse.core.task import Task, TaskPriority

logger = structlog.get_logger(__name__)


class OrchestratorAgent(Agent):
    """
    Team orchestrator that converts a feature requirement into a sprint plan.

    The canonical pipeline it generates is::

        plan → architect → developer → reviewer → qa

    Past retrospectives stored in long-term memory may add extra steps (e.g. a
    security review task) or adjust priorities.
    """

    def __init__(self, event_bus: EventBus, memory: MemoryStore) -> None:
        super().__init__(AgentRole.ORCHESTRATOR, event_bus, memory)
        self._log = logger.bind(agent="orchestrator")

    async def process(self, task: Task) -> dict[str, Any]:
        """
        Generate a sprint task graph from *task.description*.

        Returns a dict containing the list of serialised tasks.
        """
        requirement = task.description
        feature_name = task.title

        self._log.info("planning_sprint", feature=feature_name)

        # Retrieve any process guidelines stored by the learning engine
        guidelines: dict[str, Any] = self.memory.get_long("process_guidelines", {})
        extra_steps: list[str] = guidelines.get("extra_steps", [])
        priority_boost: dict[str, str] = guidelines.get("priority_boost", {})

        def _priority(role: str) -> TaskPriority:
            val = priority_boost.get(role)
            if val == "HIGH":
                return TaskPriority.HIGH
            if val == "CRITICAL":
                return TaskPriority.CRITICAL
            return TaskPriority.NORMAL

        # --- Core task graph ------------------------------------------------
        plan_task = Task(
            title=f"[Plan] {feature_name}",
            description=(
                f"Analyse the following requirement and produce a detailed "
                f"implementation plan with milestones:\n\n{requirement}"
            ),
            role=AgentRole.PLANNER.value,
            priority=TaskPriority.HIGH,
        )

        arch_task = Task(
            title=f"[Arch] {feature_name}",
            description=(
                f"Design the system architecture for:\n{requirement}\n\n"
                f"Implementation plan:\n{{plan_task.task_id}}"
            ),
            role=AgentRole.ARCHITECT.value,
            priority=_priority(AgentRole.ARCHITECT.value),
            depends_on=[plan_task.task_id],
            context={"plan_task_id": plan_task.task_id},
        )

        dev_task = Task(
            title=f"[Dev] {feature_name}",
            description=(
                f"Implement the feature based on architecture design:\n{requirement}"
            ),
            role=AgentRole.DEVELOPER.value,
            priority=_priority(AgentRole.DEVELOPER.value),
            depends_on=[arch_task.task_id],
            context={
                "plan_task_id": plan_task.task_id,
                "arch_task_id": arch_task.task_id,
            },
        )

        review_task = Task(
            title=f"[Review] {feature_name}",
            description="Perform code review, check for best practices and security.",
            role=AgentRole.REVIEWER.value,
            priority=_priority(AgentRole.REVIEWER.value),
            depends_on=[dev_task.task_id],
            context={"dev_task_id": dev_task.task_id},
        )

        qa_task = Task(
            title=f"[QA] {feature_name}",
            description=(
                "Write and execute tests. Report coverage and any defects found."
            ),
            role=AgentRole.QA.value,
            priority=_priority(AgentRole.QA.value),
            depends_on=[review_task.task_id],
            context={
                "dev_task_id": dev_task.task_id,
                "review_task_id": review_task.task_id,
            },
        )

        sprint_tasks = [plan_task, arch_task, dev_task, review_task, qa_task]

        # --- Extra steps from learning engine --------------------------------
        prev_task = qa_task
        for step_role in extra_steps:
            try:
                extra = Task(
                    title=f"[{step_role.capitalize()}] {feature_name}",
                    description=f"Perform {step_role} review for: {requirement}",
                    role=step_role,
                    priority=TaskPriority.NORMAL,
                    depends_on=[prev_task.task_id],
                )
                sprint_tasks.append(extra)
                prev_task = extra
                self._log.info("extra_step_added", role=step_role)
            except Exception:  # noqa: BLE001
                pass  # unknown role — skip

        self._log.info(
            "sprint_plan_created",
            feature=feature_name,
            task_count=len(sprint_tasks),
        )

        # Store the plan in short-term memory so other agents can reference it
        self.memory.set_short(
            "current_sprint_tasks", [t.to_dict() for t in sprint_tasks]
        )

        return {
            "feature": feature_name,
            "task_count": len(sprint_tasks),
            "tasks": [t.to_dict() for t in sprint_tasks],
        }

    # ------------------------------------------------------------------
    # Convenience factory
    # ------------------------------------------------------------------

    def create_sprint_tasks(self, title: str, description: str) -> list[Task]:
        """
        Synchronous helper to generate the task list without running the agent.

        Useful for tests and the workflow engine setup.
        """
        import asyncio
        from agentse.core.task import Task as _Task

        orchestrator_task = _Task(
            title=title, description=description, role=AgentRole.ORCHESTRATOR.value
        )

        # Run in a fresh event loop if needed
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.ensure_future(self.process(orchestrator_task))
            # Can't await here; caller should use await self.process(task) instead
            raise RuntimeError(
                "Use 'await orchestrator.process(task)' inside an async context."
            )
        except RuntimeError as exc:
            if "no running event loop" not in str(exc).lower():
                raise
        result = asyncio.run(self.process(orchestrator_task))
        tasks_data = result["tasks"]
        return [
            _Task(
                task_id=t["task_id"],
                title=t["title"],
                description=t["description"],
                role=t["role"],
                priority=TaskPriority(t["priority"]),
                depends_on=t["depends_on"],
                context=t.get("context", {}),
            )
            for t in tasks_data
        ]
