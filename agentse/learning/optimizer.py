"""
ProcessOptimizer — derives and applies process improvements from retrospectives.

Reads episodic memory (retrospective reports + QA / review data) and updates
the long-term process guidelines that the OrchestratorAgent and WorkflowEngine
use when planning the next sprint.

This is the core of the **self-learning loop**:

    Sprint N runs
        → WorkflowEngine emits RETROSPECTIVE_TRIGGERED
        → LearnerAgent calls ProcessOptimizer.optimize()
        → Guidelines updated in MemoryStore
        → Sprint N+1 uses improved guidelines
"""

from __future__ import annotations

from typing import Any

import structlog

from agentse.core.memory import MemoryStore

logger = structlog.get_logger(__name__)


class ProcessOptimizer:
    """
    Derives process improvements from historical retrospective data.

    Parameters
    ----------
    memory: Shared :class:`~agentse.core.memory.MemoryStore` instance.
    """

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory
        self._log = logger.bind(component="process_optimizer")

    def optimize(self) -> dict[str, Any]:
        """
        Analyse all available retrospective data and update process guidelines.

        Returns a dict describing what changed.
        """
        retros = self.memory.query_episodes(kind="retrospective_report", limit=20)
        qa_episodes = self.memory.query_episodes(kind="qa_completed", limit=20)
        review_episodes = self.memory.query_episodes(kind="review_completed", limit=20)

        changes: dict[str, Any] = {}

        changes.update(self._tune_coverage_target(qa_episodes))
        changes.update(self._tune_review_standards(review_episodes))
        changes.update(self._tune_process_guidelines(retros))
        changes.update(self._tune_tech_stack(retros))

        self._log.info("optimization_complete", changes=list(changes.keys()))
        return changes

    # ------------------------------------------------------------------
    # Tuning helpers
    # ------------------------------------------------------------------

    def _tune_coverage_target(
        self, qa_episodes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not qa_episodes:
            return {}

        avg_cov = sum(
            e["content"].get("coverage_pct", 80) for e in qa_episodes
        ) / len(qa_episodes)

        current_target: int = self.memory.get_long("coverage_target", 80)

        if avg_cov >= current_target + 5:
            # Team consistently exceeds target — raise the bar
            new_target = min(current_target + 5, 95)
            self.memory.set_long("coverage_target", new_target)
            self._log.info(
                "coverage_target_raised",
                from_=current_target,
                to=new_target,
                avg_coverage=round(avg_cov, 1),
            )
            return {"coverage_target": {"from": current_target, "to": new_target}}

        if avg_cov < current_target - 10:
            # Team is consistently below — slightly lower the bar to prevent
            # quality-gate blocks, then raise again gradually
            new_target = max(current_target - 5, 70)
            self.memory.set_long("coverage_target", new_target)
            self._log.info(
                "coverage_target_lowered",
                from_=current_target,
                to=new_target,
                avg_coverage=round(avg_cov, 1),
            )
            return {"coverage_target": {"from": current_target, "to": new_target}}

        return {}

    def _tune_review_standards(
        self, review_episodes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not review_episodes:
            return {}

        blocking_counts = [
            e["content"].get("blocking_count", 0) for e in review_episodes
        ]
        avg_blocking = sum(blocking_counts) / len(blocking_counts)

        current_patterns: list[str] = self.memory.get_long("known_anti_patterns", [])
        new_patterns = list(current_patterns)
        changed = False

        if avg_blocking > 2:
            # Too many blocking issues — add stricter checks
            additional = [
                "missing_docstring",
                "no_input_validation",
                "unhandled_exception",
            ]
            for p in additional:
                if p not in new_patterns:
                    new_patterns.append(p)
                    changed = True

        if changed:
            self.memory.set_long("known_anti_patterns", new_patterns)
            self._log.info(
                "anti_patterns_expanded",
                new_count=len(new_patterns),
            )
            return {
                "known_anti_patterns": {
                    "added": len(new_patterns) - len(current_patterns)
                }
            }

        return {}

    def _tune_process_guidelines(
        self, retros: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if len(retros) < 2:
            return {}

        all_actions: list[dict[str, str]] = []
        for r in retros:
            all_actions.extend(r["content"].get("action_items", []))

        # Count action item owners to identify chronic bottlenecks
        owner_counts: dict[str, int] = {}
        for a in all_actions:
            owner = a.get("owner", "unknown")
            owner_counts[owner] = owner_counts.get(owner, 0) + 1

        guidelines: dict[str, Any] = self.memory.get_long("process_guidelines", {})
        priority_boost: dict[str, str] = guidelines.get("priority_boost", {})
        changed = False

        # Boost priority for any role with 3+ recurring action items
        for owner, count in owner_counts.items():
            if count >= 3 and owner not in priority_boost:
                priority_boost[owner] = "HIGH"
                changed = True
                self._log.info("priority_boosted", role=owner, action_count=count)

        if changed:
            guidelines["priority_boost"] = priority_boost
            self.memory.set_long("process_guidelines", guidelines)
            return {"priority_boost": priority_boost}

        return {}

    def _tune_tech_stack(self, retros: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Placeholder for tech-stack evolution.

        In a real system this would analyse dependency CVEs, performance
        benchmarks, and community health metrics to recommend tech updates.
        """
        return {}
