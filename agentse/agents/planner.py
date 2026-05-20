"""
PlannerAgent — requirements analyst and task planner.

Receives a raw requirement and produces a structured implementation plan
including milestones, risks, and estimated effort.
"""

from __future__ import annotations

from typing import Any

import structlog

from agentse.core.agent import Agent, AgentRole
from agentse.core.event_bus import EventBus
from agentse.core.memory import MemoryStore
from agentse.core.task import Task

logger = structlog.get_logger(__name__)


class PlannerAgent(Agent):
    """
    Analyses requirements and produces a detailed implementation plan.

    In production this agent calls an LLM with a structured prompt.  The
    implementation below produces a deterministic plan template that is
    compatible with the full pipeline.
    """

    def __init__(self, event_bus: EventBus, memory: MemoryStore) -> None:
        super().__init__(AgentRole.PLANNER, event_bus, memory)
        self._log = logger.bind(agent="planner")

    async def process(self, task: Task) -> dict[str, Any]:
        requirement = task.description
        self._log.info("analysing_requirement", task_id=task.task_id[:8])

        # Retrieve historical complexity estimates for calibration
        past_estimates: list[dict] = self.memory.query_episodes(
            kind="plan_created", limit=10
        )
        avg_past_milestones = (
            sum(e["content"].get("milestone_count", 3) for e in past_estimates)
            / len(past_estimates)
            if past_estimates
            else 3
        )

        milestones = self._generate_milestones(requirement, int(avg_past_milestones))
        risks = self._identify_risks(requirement)
        effort_days = self._estimate_effort(requirement)

        plan = {
            "requirement_summary": requirement[:200],
            "milestones": milestones,
            "risks": risks,
            "estimated_effort_days": effort_days,
            "milestone_count": len(milestones),
        }

        self._log.info(
            "plan_created",
            milestones=len(milestones),
            effort_days=effort_days,
        )

        self.memory.record_episode(
            kind="plan_created",
            content=plan,
            agent_id=self.agent_id,
            tags=["planning", task.sprint_id or ""],
        )

        return plan

    # ------------------------------------------------------------------

    def _generate_milestones(self, requirement: str, count: int = 3) -> list[str]:
        base = [
            "M1: Requirements finalised and acceptance criteria agreed",
            "M2: Architecture design approved",
            "M3: Core implementation complete",
            "M4: Code review passed",
            "M5: All tests passing with ≥80% coverage",
        ]
        return base[:max(count, 3)]

    def _identify_risks(self, requirement: str) -> list[dict[str, str]]:
        risks = [
            {
                "risk": "Scope creep",
                "probability": "medium",
                "mitigation": "Strict change-request process",
            },
            {
                "risk": "Integration complexity",
                "probability": "low",
                "mitigation": "Early spike and prototype",
            },
        ]
        keywords = requirement.lower()
        if any(w in keywords for w in ["database", "db", "sql", "postgres", "mysql"]):
            risks.append(
                {
                    "risk": "Data migration",
                    "probability": "high",
                    "mitigation": "Automated migration scripts with rollback",
                }
            )
        if any(w in keywords for w in ["auth", "security", "login", "token"]):
            risks.append(
                {
                    "risk": "Security vulnerability",
                    "probability": "medium",
                    "mitigation": "Security audit and penetration testing",
                }
            )
        return risks

    def _estimate_effort(self, requirement: str) -> int:
        words = len(requirement.split())
        # Rough heuristic: 1 day per 20 words of requirement, capped at 30
        return min(max(words // 20, 1), 30)
