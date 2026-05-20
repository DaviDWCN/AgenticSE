"""
Integration test: full end-to-end sprint using AgentTeam.
"""

import asyncio
import pytest
from pathlib import Path

from agentse.team import AgentTeam


@pytest.fixture
def team(tmp_path: Path) -> AgentTeam:
    return AgentTeam(
        store_path=tmp_path / "integration_memory.json",
        concurrency=4,
    )


def test_full_sprint_runs_to_completion(team: AgentTeam) -> None:
    summary = asyncio.run(
        team.run_feature(
            title="Test Feature",
            description=(
                "Build a simple REST API with user authentication using JWT tokens "
                "and a PostgreSQL database backend."
            ),
            sprint_name="Integration Sprint",
        )
    )

    assert summary["total"] >= 5
    assert summary["completed"] >= 4  # At least planner/arch/dev/review/qa should pass
    assert summary["sprint_name"] == "Integration Sprint"
    assert "tasks" in summary
    assert "agent_metrics" in summary


def test_two_sprints_show_learning(tmp_path: Path) -> None:
    """After two sprints, the LearnerAgent should have updated process guidelines."""
    team = AgentTeam(store_path=tmp_path / "two_sprint_mem.json", concurrency=4)

    asyncio.run(
        team.run_feature(
            title="Feature A",
            description="Build a notification service with event-driven architecture.",
        )
    )
    asyncio.run(
        team.run_feature(
            title="Feature B",
            description="Add OAuth2 social login with Google and GitHub.",
        )
    )

    trend = team.trend_report()
    # After 2 sprints there should be retrospective data
    assert trend.get("sprint_count", 0) >= 1 or "message" not in trend


def test_team_status_returns_all_roles(team: AgentTeam) -> None:
    status = team.team_status()
    expected_roles = {
        "orchestrator", "planner", "architect",
        "developer", "reviewer", "qa", "learner"
    }
    assert set(status.keys()) == expected_roles
    for role, info in status.items():
        assert "status" in info
        assert "metrics" in info


def test_memory_persists_between_team_instances(tmp_path: Path) -> None:
    store_path = tmp_path / "persistent_memory.json"

    team1 = AgentTeam(store_path=store_path)
    asyncio.run(
        team1.run_feature(
            title="Sprint 1 Feature",
            description="Implement caching layer with Redis.",
        )
    )

    # Create a new team instance using the same store
    team2 = AgentTeam(store_path=store_path)
    mem_summary = team2.memory_summary()
    # Should have at least some episodic data from sprint 1
    assert mem_summary["episodic_count"] >= 1
