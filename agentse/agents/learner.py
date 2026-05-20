"""
LearnerAgent — self-learning and process improvement engine.

After each sprint the workflow engine publishes a RETROSPECTIVE_TRIGGERED
event.  The LearnerAgent handles this event and:

1. Analyses the sprint summary (task durations, failure rates, defects).
2. Derives improvement actions.
3. Updates the shared MemoryStore with new process guidelines, coding
   standards, and anti-patterns.
4. Publishes a PROCESS_IMPROVED event so the team knows the process has
   been updated.

Over multiple sprints this creates a compounding improvement loop.
"""

from __future__ import annotations

from typing import Any

import structlog

from agentse.core.agent import Agent, AgentRole
from agentse.core.event_bus import Event, EventBus, EventType
from agentse.core.memory import MemoryStore
from agentse.core.task import Task

logger = structlog.get_logger(__name__)


class LearnerAgent(Agent):
    """
    Self-learning agent that analyses retrospective data and improves the
    team's process guidelines stored in long-term memory.
    """

    def __init__(self, event_bus: EventBus, memory: MemoryStore) -> None:
        super().__init__(AgentRole.LEARNER, event_bus, memory)
        self._log = logger.bind(agent="learner")
        # Subscribe to retrospective events automatically
        self.event_bus.subscribe(
            EventType.RETROSPECTIVE_TRIGGERED, self._on_retrospective
        )

    # ------------------------------------------------------------------
    # Event handler — called automatically after each sprint
    # ------------------------------------------------------------------

    async def _on_retrospective(self, event: Event) -> None:
        """React to a RETROSPECTIVE_TRIGGERED event."""
        summary: dict[str, Any] = event.payload.get("summary", {})
        sprint_id: str = event.payload.get("sprint_id", "unknown")
        self._log.info("retrospective_received", sprint_id=sprint_id)

        task = Task(
            title=f"Retrospective for {sprint_id}",
            description=str(summary),
            role=AgentRole.LEARNER.value,
            sprint_id=sprint_id,
        )
        task.context["sprint_summary"] = summary
        await self.run(task)

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    async def process(self, task: Task) -> dict[str, Any]:
        summary: dict[str, Any] = task.context.get("sprint_summary", {})
        sprint_id = task.sprint_id or "unknown"

        self._log.info("analysing_sprint", sprint_id=sprint_id)

        improvements = self._analyse(summary)
        self._apply_improvements(improvements)

        self._log.info(
            "improvements_applied",
            count=len(improvements),
            sprint_id=sprint_id,
        )

        self.memory.record_episode(
            kind="retrospective",
            content={
                "sprint_id": sprint_id,
                "improvements": improvements,
                "metrics": {
                    "completed": summary.get("completed", 0),
                    "failed": summary.get("failed", 0),
                    "avg_duration_s": summary.get("avg_task_duration_s", 0),
                },
            },
            agent_id=self.agent_id,
            tags=["learning", "retrospective", sprint_id],
        )

        await self.event_bus.publish(
            Event(
                event_type=EventType.PROCESS_IMPROVED,
                source=self.agent_id,
                payload={
                    "sprint_id": sprint_id,
                    "improvement_count": len(improvements),
                    "improvements": improvements,
                },
            )
        )

        return {
            "sprint_id": sprint_id,
            "improvements_applied": len(improvements),
            "improvements": improvements,
        }

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    def _analyse(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        improvements: list[dict[str, Any]] = []
        total = summary.get("total", 1) or 1
        failed = summary.get("failed", 0)
        avg_duration = summary.get("avg_task_duration_s", 0.0)

        failure_rate = failed / total

        # High failure rate → tighten review standards
        if failure_rate > 0.3:
            improvements.append(
                {
                    "area": "review",
                    "finding": f"High task failure rate ({failure_rate:.0%})",
                    "action": "add_extra_step",
                    "value": AgentRole.REVIEWER.value,
                    "rationale": "Extra review pass to catch issues earlier",
                }
            )

        # Slow tasks → boost priority of slow roles
        if avg_duration > 5.0:
            improvements.append(
                {
                    "area": "scheduling",
                    "finding": f"Average task duration {avg_duration:.1f}s is high",
                    "action": "boost_priority",
                    "value": {AgentRole.DEVELOPER.value: "HIGH"},
                    "rationale": "Prioritise development tasks to reduce cycle time",
                }
            )

        # Analyse agent metrics for bottlenecks
        agent_metrics: dict[str, Any] = summary.get("agent_metrics", {})
        for role, metrics in agent_metrics.items():
            sr = metrics.get("success_rate", 1.0)
            if sr < 0.7:
                improvements.append(
                    {
                        "area": "reliability",
                        "finding": f"{role} agent success rate is {sr:.0%}",
                        "action": "increase_max_attempts",
                        "value": {"role": role, "max_attempts": 5},
                        "rationale": "Increase retries for flaky agent",
                    }
                )

        # Check QA episodes for low coverage
        recent_qa = self.memory.query_episodes(kind="qa_completed", limit=5)
        if recent_qa:
            avg_coverage = sum(
                e["content"].get("coverage_pct", 80) for e in recent_qa
            ) / len(recent_qa)
            if avg_coverage < 75:
                improvements.append(
                    {
                        "area": "quality",
                        "finding": f"Average test coverage {avg_coverage:.0f}% is below target",
                        "action": "raise_coverage_target",
                        "value": int(avg_coverage + 5),
                        "rationale": "Incrementally raise coverage bar",
                    }
                )

        return improvements

    def _apply_improvements(self, improvements: list[dict[str, Any]]) -> None:
        """Persist each improvement into long-term memory."""
        guidelines: dict[str, Any] = self.memory.get_long("process_guidelines", {})
        extra_steps: list[str] = guidelines.get("extra_steps", [])
        priority_boost: dict[str, str] = guidelines.get("priority_boost", {})

        for imp in improvements:
            action = imp.get("action")
            value = imp.get("value")

            if action == "add_extra_step" and isinstance(value, str):
                if value not in extra_steps:
                    extra_steps.append(value)
                    self._log.info("extra_step_added", step=value)

            elif action == "boost_priority" and isinstance(value, dict):
                priority_boost.update(value)
                self._log.info("priority_boosted", updates=value)

            elif action == "raise_coverage_target" and isinstance(value, int):
                self.memory.set_long("coverage_target", value)
                self._log.info("coverage_target_raised", target=value)

        guidelines["extra_steps"] = extra_steps
        guidelines["priority_boost"] = priority_boost
        self.memory.set_long("process_guidelines", guidelines)

    # ------------------------------------------------------------------
    # Trend reporting
    # ------------------------------------------------------------------

    def generate_trend_report(self) -> dict[str, Any]:
        """Return a summary of all retrospectives for dashboard use."""
        retros = self.memory.query_episodes(kind="retrospective")
        if not retros:
            return {"message": "No retrospectives recorded yet"}

        all_improvements: list[dict] = []
        for r in retros:
            all_improvements.extend(r["content"].get("improvements", []))

        area_counts: dict[str, int] = {}
        for imp in all_improvements:
            area = imp.get("area", "unknown")
            area_counts[area] = area_counts.get(area, 0) + 1

        return {
            "sprint_count": len(retros),
            "total_improvements": len(all_improvements),
            "improvement_areas": area_counts,
            "process_guidelines": self.memory.get_long("process_guidelines", {}),
            "coverage_target": self.memory.get_long("coverage_target", 80),
        }
