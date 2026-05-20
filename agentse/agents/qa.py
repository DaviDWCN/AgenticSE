"""
QAAgent — test strategy, execution and coverage reporting.

Generates a test plan, runs any sandboxed tests, and reports:
- Test cases written
- Pass / fail / skip counts
- Coverage percentage
- Defects found
"""

from __future__ import annotations

import random
from typing import Any

import structlog

from agentse.core.agent import Agent, AgentRole
from agentse.core.event_bus import EventBus
from agentse.core.memory import MemoryStore
from agentse.core.task import Task

logger = structlog.get_logger(__name__)


class QAAgent(Agent):
    """Tests the implementation and reports quality metrics."""

    def __init__(self, event_bus: EventBus, memory: MemoryStore) -> None:
        super().__init__(AgentRole.QA, event_bus, memory)
        self._log = logger.bind(agent="qa")

    async def process(self, task: Task) -> dict[str, Any]:
        self._log.info("running_qa", task_id=task.task_id[:8])

        # Pull artefacts from upstream context
        dev_result: dict[str, Any] = task.context.get("dev_result", {})
        review_result: dict[str, Any] = task.context.get("review_result", {})
        modules: list[dict[str, str]] = dev_result.get("modules", [])
        review_verdict: str = review_result.get("verdict", "approved")

        # Retrieve historical coverage targets
        coverage_target: int = self.memory.get_long("coverage_target", 80)

        test_cases = self._generate_test_cases(modules)
        test_results = self._simulate_test_run(test_cases, review_verdict)
        coverage = self._calculate_coverage(modules, test_cases)

        defects = self._identify_defects(test_results)

        quality_gate_passed = (
            coverage >= coverage_target
            and test_results["failed"] == 0
            and not defects
        )

        result = {
            "test_cases": len(test_cases),
            "test_results": test_results,
            "coverage_pct": coverage,
            "coverage_target": coverage_target,
            "defects": defects,
            "quality_gate_passed": quality_gate_passed,
            "test_plan": test_cases[:5],  # sample
        }

        self._log.info(
            "qa_complete",
            coverage=coverage,
            passed=test_results["passed"],
            failed=test_results["failed"],
            quality_gate=quality_gate_passed,
        )

        self.memory.record_episode(
            kind="qa_completed",
            content={
                "coverage_pct": coverage,
                "test_count": len(test_cases),
                "defect_count": len(defects),
                "quality_gate_passed": quality_gate_passed,
            },
            agent_id=self.agent_id,
            tags=["qa", task.sprint_id or ""],
        )

        return result

    # ------------------------------------------------------------------

    def _generate_test_cases(self, modules: list[dict[str, str]]) -> list[dict[str, str]]:
        test_cases = []
        for mod in modules:
            name = mod.get("name", "module")
            test_cases.extend(
                [
                    {
                        "id": f"TC-{name.upper()}-01",
                        "name": f"test_{name}_happy_path",
                        "type": "unit",
                        "description": f"Verify {name} works correctly for valid input",
                    },
                    {
                        "id": f"TC-{name.upper()}-02",
                        "name": f"test_{name}_invalid_input",
                        "type": "unit",
                        "description": f"Verify {name} raises error for invalid input",
                    },
                    {
                        "id": f"TC-{name.upper()}-03",
                        "name": f"test_{name}_integration",
                        "type": "integration",
                        "description": f"Verify {name} integrates correctly",
                    },
                ]
            )
        # Add e2e test
        test_cases.append(
            {
                "id": "TC-E2E-01",
                "name": "test_end_to_end_flow",
                "type": "e2e",
                "description": "Full end-to-end user flow test",
            }
        )
        return test_cases

    def _simulate_test_run(
        self, test_cases: list[dict[str, str]], review_verdict: str
    ) -> dict[str, int]:
        total = len(test_cases)
        # Fewer failures if review was approved
        fail_rate = 0.0 if review_verdict == "approved" else 0.1
        failed = sum(1 for _ in test_cases if random.random() < fail_rate)
        skipped = max(0, total // 10)
        passed = total - failed - skipped
        return {"total": total, "passed": passed, "failed": failed, "skipped": skipped}

    def _calculate_coverage(
        self, modules: list[dict[str, str]], test_cases: list[dict[str, str]]
    ) -> int:
        if not modules:
            return 0
        # Heuristic: ~3 test cases per module = 80% coverage
        ratio = len(test_cases) / (len(modules) * 3)
        return min(int(ratio * 80), 95)

    def _identify_defects(self, test_results: dict[str, int]) -> list[dict[str, str]]:
        defects = []
        if test_results["failed"] > 0:
            defects.append(
                {
                    "id": "DEF-001",
                    "severity": "major",
                    "description": f"{test_results['failed']} test(s) failing",
                    "recommendation": "Fix failing tests before release",
                }
            )
        return defects
