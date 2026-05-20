"""
AgentTeam — convenience factory that wires the full engineering team.

Instantiates all seven agents, registers them with the workflow engine,
and exposes a single ``run_feature`` coroutine for end-to-end execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from agentse.agents import (
    ArchitectAgent,
    DeveloperAgent,
    LearnerAgent,
    OrchestratorAgent,
    PlannerAgent,
    QAAgent,
    ReviewerAgent,
)
from agentse.core.event_bus import EventBus
from agentse.core.memory import MemoryStore
from agentse.core.task import Task, TaskPriority
from agentse.core.workflow import WorkflowEngine
from agentse.learning.optimizer import ProcessOptimizer
from agentse.learning.retrospective import SprintRetrospective

logger = structlog.get_logger(__name__)


class AgentTeam:
    """
    A fully wired autonomous engineering team.

    Parameters
    ----------
    store_path: Path to the persistent memory store file.
    concurrency: Maximum number of tasks executing simultaneously.
    """

    def __init__(
        self,
        store_path: Path | str | None = None,
        concurrency: int = 4,
    ) -> None:
        self.memory = MemoryStore(store_path=store_path)
        self.event_bus = EventBus()
        self.engine = WorkflowEngine(self.event_bus, self.memory)
        self.concurrency = concurrency

        # Instantiate all agents
        self.orchestrator = OrchestratorAgent(self.event_bus, self.memory)
        self.planner = PlannerAgent(self.event_bus, self.memory)
        self.architect = ArchitectAgent(self.event_bus, self.memory)
        self.developer = DeveloperAgent(self.event_bus, self.memory)
        self.reviewer = ReviewerAgent(self.event_bus, self.memory)
        self.qa = QAAgent(self.event_bus, self.memory)
        self.learner = LearnerAgent(self.event_bus, self.memory)  # auto-subscribes

        # Register all agents with the workflow engine
        for agent in [
            self.orchestrator,
            self.planner,
            self.architect,
            self.developer,
            self.reviewer,
            self.qa,
            self.learner,
        ]:
            self.engine.register_agent(agent)

        # Attach auxiliary learning utilities
        self.retrospective = SprintRetrospective(self.memory)
        self.optimizer = ProcessOptimizer(self.memory)

        self._log = logger.bind(component="agent_team")

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    async def run_feature(
        self,
        title: str,
        description: str,
        sprint_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Plan and execute a complete feature from requirement to QA.

        The orchestrator generates the task graph; the workflow engine
        dispatches each task to the correct agent in dependency order.
        After completion the learning engine analyses the sprint and
        improves future process guidelines.

        Returns the full sprint summary dict.
        """
        sprint_name = sprint_name or f"Sprint: {title}"
        self._log.info("feature_started", title=title)

        # Step 1: Orchestrator generates the task graph
        orchestrator_task = Task(
            title=title,
            description=description,
            role=self.orchestrator.role.value,
        )
        orchestrator_result = await self.orchestrator.run(orchestrator_task)
        tasks_data: list[dict[str, Any]] = orchestrator_result["tasks"]

        # Reconstruct Task objects from serialised dicts
        tasks = [
            Task(
                task_id=t["task_id"],
                title=t["title"],
                description=t["description"],
                role=t["role"],
                priority=TaskPriority(t["priority"]),
                depends_on=t["depends_on"],
                context=t.get("context", {}),
                max_attempts=t.get("max_attempts", 3),
            )
            for t in tasks_data
        ]

        # Step 2: Run the sprint
        summary = await self.engine.run_sprint(
            sprint_name=sprint_name,
            tasks=tasks,
            concurrency=self.concurrency,
        )

        # Step 3: Run the process optimizer (complements the learner agent)
        optimization_changes = self.optimizer.optimize()
        if optimization_changes:
            self._log.info(
                "process_optimized", changes=list(optimization_changes.keys())
            )

        return summary

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def team_status(self) -> dict[str, Any]:
        """Return the current status of every agent in the team."""
        return {
            agent.role.value: agent.describe()
            for agent in [
                self.orchestrator,
                self.planner,
                self.architect,
                self.developer,
                self.reviewer,
                self.qa,
                self.learner,
            ]
        }

    def trend_report(self) -> dict[str, Any]:
        """Return a learning trend report across all sprints."""
        return self.learner.generate_trend_report()

    def memory_summary(self) -> dict[str, Any]:
        """Return a summary of the shared memory store."""
        return self.memory.summary()
