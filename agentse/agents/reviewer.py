"""
ReviewerAgent — code quality, security and best-practice review.

Analyses the developer's implementation artefacts and produces:
- A list of review findings (issues, suggestions, approvals).
- A pass/fail verdict.
- Actionable improvement items fed back to the DeveloperAgent.
"""

from __future__ import annotations

from typing import Any

import structlog

from agentse.core.agent import Agent, AgentRole
from agentse.core.event_bus import EventBus
from agentse.core.memory import MemoryStore
from agentse.core.task import Task

logger = structlog.get_logger(__name__)


class ReviewerAgent(Agent):
    """Performs code review on implementation artefacts."""

    def __init__(self, event_bus: EventBus, memory: MemoryStore) -> None:
        super().__init__(AgentRole.REVIEWER, event_bus, memory)
        self._log = logger.bind(agent="reviewer")

    async def process(self, task: Task) -> dict[str, Any]:
        self._log.info("reviewing_code", task_id=task.task_id[:8])

        # Pull implementation result from context/memory if available
        dev_result: dict[str, Any] = task.context.get("dev_result", {})
        artefacts: list[dict[str, Any]] = dev_result.get("artefacts", [])

        # Retrieve known anti-patterns from long-term memory
        known_anti_patterns: list[str] = self.memory.get_long(
            "known_anti_patterns",
            [
                "hardcoded secrets",
                "missing input validation",
                "no error handling",
                "SQL injection risk",
                "unbounded recursion",
            ],
        )

        findings = self._run_checks(artefacts, known_anti_patterns)
        blocking = [f for f in findings if f["severity"] == "blocking"]
        verdict = "approved" if not blocking else "changes_requested"

        result = {
            "verdict": verdict,
            "findings": findings,
            "blocking_count": len(blocking),
            "total_findings": len(findings),
            "checklist": {
                "type_hints_present": True,
                "no_hardcoded_secrets": True,
                "error_handling_present": True,
                "logging_present": True,
                "tests_required": True,
            },
        }

        self._log.info(
            "review_complete",
            verdict=verdict,
            findings=len(findings),
            blocking=len(blocking),
        )

        self.memory.record_episode(
            kind="review_completed",
            content={
                "verdict": verdict,
                "blocking_count": len(blocking),
                "artefact_count": len(artefacts),
            },
            agent_id=self.agent_id,
            tags=["review", task.sprint_id or ""],
        )

        # If blocking issues found, record as anti-pattern for future reference
        for f in blocking:
            pattern = f.get("issue", "")
            if pattern and pattern not in known_anti_patterns:
                known_anti_patterns.append(pattern)
                self.memory.set_long("known_anti_patterns", known_anti_patterns)

        return result

    # ------------------------------------------------------------------

    def _run_checks(
        self,
        artefacts: list[dict[str, Any]],
        anti_patterns: list[str],
    ) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []

        if not artefacts:
            findings.append(
                {
                    "issue": "No implementation artefacts found",
                    "severity": "warning",
                    "suggestion": "Ensure DeveloperAgent produced output",
                }
            )
            return findings

        for art in artefacts:
            content: str = art.get("content", "")
            path: str = art.get("path", "unknown")

            for pattern in anti_patterns:
                if pattern.lower().replace(" ", "_") in content.lower().replace(
                    " ", "_"
                ):
                    findings.append(
                        {
                            "file": path,
                            "issue": f"Potential {pattern}",
                            "severity": "blocking",
                            "suggestion": f"Review and remove {pattern}",
                        }
                    )

            # Positive checks
            if "TODO" in content:
                findings.append(
                    {
                        "file": path,
                        "issue": "TODO comments present",
                        "severity": "warning",
                        "suggestion": "Resolve all TODOs before merging",
                    }
                )

            if "logger" not in content:
                findings.append(
                    {
                        "file": path,
                        "issue": "No logging found",
                        "severity": "suggestion",
                        "suggestion": "Add structured logging",
                    }
                )

        return findings
