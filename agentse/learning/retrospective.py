"""
SprintRetrospective — structured analysis of a completed sprint.

Produces a human-readable and machine-readable retrospective report
covering: what went well, what went poorly, and specific action items.

The analysis draws on episodic memory (task durations, defect counts,
review findings) so that the retrospective is grounded in real data rather
than opinion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from agentse.core.memory import MemoryStore

logger = structlog.get_logger(__name__)


class SprintRetrospective:
    """
    Analyses a sprint summary and produces a retrospective report.

    Parameters
    ----------
    memory: Shared :class:`~agentse.core.memory.MemoryStore` instance.
    """

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory
        self._log = logger.bind(component="retrospective")

    def analyse(self, sprint_summary: dict[str, Any]) -> dict[str, Any]:
        """
        Generate a retrospective report for *sprint_summary*.

        Returns a structured dict with sections: went_well, went_poorly,
        action_items, and metrics.
        """
        sprint_id = sprint_summary.get("sprint_id", "unknown")
        self._log.info("analysing_sprint", sprint_id=sprint_id)

        tasks: list[dict[str, Any]] = sprint_summary.get("tasks", [])
        agent_metrics: dict[str, Any] = sprint_summary.get("agent_metrics", {})

        went_well = self._identify_positives(sprint_summary, tasks, agent_metrics)
        went_poorly = self._identify_negatives(sprint_summary, tasks, agent_metrics)
        action_items = self._derive_actions(went_poorly)

        report = {
            "sprint_id": sprint_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "total_tasks": sprint_summary.get("total", 0),
                "completed": sprint_summary.get("completed", 0),
                "failed": sprint_summary.get("failed", 0),
                "cancelled": sprint_summary.get("cancelled", 0),
                "avg_task_duration_s": sprint_summary.get("avg_task_duration_s", 0),
            },
            "went_well": went_well,
            "went_poorly": went_poorly,
            "action_items": action_items,
        }

        self.memory.record_episode(
            kind="retrospective_report",
            content=report,
            tags=["retrospective", sprint_id],
        )

        return report

    # ------------------------------------------------------------------

    def _identify_positives(
        self,
        summary: dict[str, Any],
        tasks: list[dict[str, Any]],
        agent_metrics: dict[str, Any],
    ) -> list[str]:
        positives = []
        total = summary.get("total", 1) or 1
        completed = summary.get("completed", 0)

        completion_rate = completed / total
        if completion_rate >= 0.9:
            positives.append(
                f"High task completion rate: {completion_rate:.0%} of tasks completed"
            )

        for role, metrics in agent_metrics.items():
            sr = metrics.get("success_rate", 0)
            if sr >= 0.95:
                positives.append(
                    f"{role.capitalize()} agent achieved {sr:.0%} success rate"
                )

        # Check QA coverage
        recent_qa = self.memory.query_episodes(kind="qa_completed", limit=3)
        for ep in recent_qa:
            cov = ep["content"].get("coverage_pct", 0)
            if cov >= 80:
                positives.append(f"Test coverage reached {cov}% (target: 80%)")

        if not positives:
            positives.append("Sprint completed without critical blockers")

        return positives

    def _identify_negatives(
        self,
        summary: dict[str, Any],
        tasks: list[dict[str, Any]],
        agent_metrics: dict[str, Any],
    ) -> list[str]:
        negatives = []
        total = summary.get("total", 1) or 1
        failed = summary.get("failed", 0)
        avg_dur = summary.get("avg_task_duration_s", 0.0)

        if failed > 0:
            negatives.append(
                f"{failed} task(s) failed ({failed / total:.0%} failure rate)"
            )

        if avg_dur > 10.0:
            negatives.append(
                f"Average task duration was {avg_dur:.1f}s — pipeline may be slow"
            )

        for role, metrics in agent_metrics.items():
            sr = metrics.get("success_rate", 1.0)
            if sr < 0.8:
                negatives.append(
                    f"{role.capitalize()} agent had low success rate: {sr:.0%}"
                )

        # Check for defects
        recent_qa = self.memory.query_episodes(kind="qa_completed", limit=3)
        for ep in recent_qa:
            defects = ep["content"].get("defect_count", 0)
            if defects > 0:
                negatives.append(f"QA found {defects} defect(s)")
            cov = ep["content"].get("coverage_pct", 100)
            if cov < 80:
                negatives.append(
                    f"Test coverage {cov}% is below the 80% target"
                )

        return negatives

    def _derive_actions(self, negatives: list[str]) -> list[dict[str, str]]:
        actions = []
        for neg in negatives:
            neg_lower = neg.lower()
            if "fail" in neg_lower:
                actions.append(
                    {
                        "priority": "high",
                        "owner": "developer",
                        "action": "Investigate and fix root cause of task failures",
                        "trigger": neg,
                    }
                )
            if "coverage" in neg_lower:
                actions.append(
                    {
                        "priority": "medium",
                        "owner": "qa",
                        "action": "Add missing test cases to reach coverage target",
                        "trigger": neg,
                    }
                )
            if "slow" in neg_lower or "duration" in neg_lower:
                actions.append(
                    {
                        "priority": "medium",
                        "owner": "orchestrator",
                        "action": "Profile and optimise slow agent tasks",
                        "trigger": neg,
                    }
                )
            if "defect" in neg_lower:
                actions.append(
                    {
                        "priority": "high",
                        "owner": "developer",
                        "action": "Triage and fix all reported defects",
                        "trigger": neg,
                    }
                )
        return actions
