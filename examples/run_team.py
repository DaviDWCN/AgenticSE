"""
Example: Run a complete end-to-end autonomous engineering sprint.

This demonstrates the full AgenticSE pipeline:

1. OrchestratorAgent reads the requirement and generates a task graph.
2. WorkflowEngine dispatches tasks in dependency order.
3. PlannerAgent → ArchitectAgent → DeveloperAgent → ReviewerAgent → QAAgent
4. LearnerAgent automatically analyses the sprint and updates process guidelines.
5. A second sprint shows how the team has evolved its own process.

Run with:
    python examples/run_team.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Make sure the package is importable when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ]
)

from agentse.team import AgentTeam


async def main() -> None:
    print("\n" + "=" * 70)
    print("  AgenticSE — Autonomous Multi-Agent Software Engineering Team")
    print("=" * 70 + "\n")

    # Use a temporary store so each run starts fresh
    store_path = Path("/tmp/agentse_example_memory.json")
    store_path.unlink(missing_ok=True)

    team = AgentTeam(store_path=store_path, concurrency=4)

    # ------------------------------------------------------------------ #
    #  Sprint 1: Build a user authentication feature                       #
    # ------------------------------------------------------------------ #
    print("▶  Sprint 1: User Authentication Feature\n")

    summary1 = await team.run_feature(
        title="User Authentication",
        description=(
            "Build a secure user authentication system with JWT tokens, "
            "refresh token rotation, password hashing (bcrypt), and "
            "rate-limiting on the login endpoint. "
            "Must support OAuth2 social login (Google, GitHub). "
            "Store user data in PostgreSQL with encrypted sensitive fields."
        ),
        sprint_name="Sprint 1 — Auth",
    )

    _print_sprint_summary("Sprint 1", summary1)

    # ------------------------------------------------------------------ #
    #  Sprint 2: Event-driven notification service                         #
    # ------------------------------------------------------------------ #
    print("\n▶  Sprint 2: Event-Driven Notification Service\n")

    summary2 = await team.run_feature(
        title="Notification Service",
        description=(
            "Build an event-driven notification service that listens to "
            "Redis Streams for user events (signup, purchase, alert) and "
            "sends email / SMS / push notifications. "
            "Include retry logic, delivery receipts, and an admin dashboard."
        ),
        sprint_name="Sprint 2 — Notifications",
    )

    _print_sprint_summary("Sprint 2", summary2)

    # ------------------------------------------------------------------ #
    #  Show learning evolution                                             #
    # ------------------------------------------------------------------ #
    print("\n▶  Learning Trend Report (after 2 sprints)\n")
    trend = team.trend_report()
    print(json.dumps(trend, indent=2, default=str))

    print("\n▶  Memory Store Summary\n")
    mem = team.memory_summary()
    print(json.dumps(mem, indent=2, default=str))

    print("\n" + "=" * 70)
    print("  Run complete!  The team's process guidelines have been updated.")
    print("  Run again to see the evolved process applied to a new sprint.")
    print("=" * 70 + "\n")


def _print_sprint_summary(name: str, summary: dict) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {name} Results")
    print(f"{'─' * 50}")
    print(f"  Total tasks:   {summary['total']}")
    print(f"  Completed:     {summary['completed']}")
    print(f"  Failed:        {summary['failed']}")
    print(f"  Cancelled:     {summary['cancelled']}")
    print(f"  Avg duration:  {summary['avg_task_duration_s']:.3f}s")
    print()


if __name__ == "__main__":
    asyncio.run(main())
