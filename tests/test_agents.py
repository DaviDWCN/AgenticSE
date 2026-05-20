"""
Tests for individual agents.
"""

import asyncio
import pytest
from pathlib import Path

from agentse.core.event_bus import EventBus
from agentse.core.memory import MemoryStore
from agentse.core.task import Task, TaskStatus


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStore:
    return MemoryStore(store_path=tmp_path / "test_mem.json")


@pytest.fixture
def sample_task() -> Task:
    return Task(
        title="Test feature",
        description="Build a test feature with user auth and database storage",
        role="developer",
    )


# ------------------------------------------------------------------ #
# PlannerAgent                                                         #
# ------------------------------------------------------------------ #


def test_planner_agent_process(bus, memory, sample_task) -> None:
    from agentse.agents.planner import PlannerAgent

    planner = PlannerAgent(bus, memory)
    result = asyncio.run(planner.process(sample_task))

    assert "milestones" in result
    assert "risks" in result
    assert "estimated_effort_days" in result
    assert len(result["milestones"]) >= 3
    assert result["estimated_effort_days"] >= 1


def test_planner_risk_detection(bus, memory) -> None:
    from agentse.agents.planner import PlannerAgent

    planner = PlannerAgent(bus, memory)
    task = Task(
        title="Auth feature",
        description="Build login with JWT tokens and PostgreSQL database",
        role="planner",
    )
    result = asyncio.run(planner.process(task))

    risk_descriptions = [r["risk"] for r in result["risks"]]
    # Should detect both auth and database risks
    assert any("Data migration" in r or "Security" in r for r in risk_descriptions)


# ------------------------------------------------------------------ #
# ArchitectAgent                                                       #
# ------------------------------------------------------------------ #


def test_architect_agent_process(bus, memory, sample_task) -> None:
    from agentse.agents.architect import ArchitectAgent

    architect = ArchitectAgent(bus, memory)
    result = asyncio.run(architect.process(sample_task))

    assert "tech_stack" in result
    assert "components" in result
    assert "interfaces" in result
    assert "data_models" in result
    assert len(result["components"]) >= 4


def test_architect_uses_memory_tech_stack(bus, memory, sample_task) -> None:
    from agentse.agents.architect import ArchitectAgent

    custom_stack = {"language": "Go", "framework": "Gin", "database": "CockroachDB"}
    memory.set_long("preferred_tech_stack", custom_stack)

    architect = ArchitectAgent(bus, memory)
    result = asyncio.run(architect.process(sample_task))

    assert result["tech_stack"]["language"] == "Go"
    assert result["tech_stack"]["framework"] == "Gin"


# ------------------------------------------------------------------ #
# DeveloperAgent                                                       #
# ------------------------------------------------------------------ #


def test_developer_agent_process(bus, memory, sample_task) -> None:
    from agentse.agents.developer import DeveloperAgent

    dev = DeveloperAgent(bus, memory)
    result = asyncio.run(dev.process(sample_task))

    assert "modules" in result
    assert "artefacts" in result
    assert len(result["modules"]) >= 4
    assert len(result["artefacts"]) == len(result["modules"])


def test_developer_module_skeletons_have_logger(bus, memory, sample_task) -> None:
    from agentse.agents.developer import DeveloperAgent

    dev = DeveloperAgent(bus, memory)
    result = asyncio.run(dev.process(sample_task))

    for art in result["artefacts"]:
        assert "logger" in art["content"], f"Missing logger in {art['path']}"


# ------------------------------------------------------------------ #
# ReviewerAgent                                                        #
# ------------------------------------------------------------------ #


def test_reviewer_agent_approved(bus, memory) -> None:
    from agentse.agents.reviewer import ReviewerAgent
    from agentse.agents.developer import DeveloperAgent

    dev = DeveloperAgent(bus, memory)
    dev_task = Task(
        title="Build feature", description="Basic REST API", role="developer"
    )
    dev_result = asyncio.run(dev.process(dev_task))

    reviewer = ReviewerAgent(bus, memory)
    review_task = Task(
        title="Review feature",
        description="Review the code",
        role="reviewer",
        context={"dev_result": dev_result},
    )
    result = asyncio.run(reviewer.process(review_task))

    assert "verdict" in result
    assert result["verdict"] in ("approved", "changes_requested")
    assert "findings" in result
    assert isinstance(result["findings"], list)


def test_reviewer_no_artefacts_produces_warning(bus, memory) -> None:
    from agentse.agents.reviewer import ReviewerAgent

    reviewer = ReviewerAgent(bus, memory)
    task = Task(
        title="Review empty",
        description="Review",
        role="reviewer",
        context={"dev_result": {}},
    )
    result = asyncio.run(reviewer.process(task))

    assert any(f["severity"] == "warning" for f in result["findings"])


# ------------------------------------------------------------------ #
# QAAgent                                                              #
# ------------------------------------------------------------------ #


def test_qa_agent_process(bus, memory) -> None:
    from agentse.agents.qa import QAAgent
    from agentse.agents.developer import DeveloperAgent

    dev = DeveloperAgent(bus, memory)
    dev_task = Task(
        title="Build", description="REST API with auth", role="developer"
    )
    dev_result = asyncio.run(dev.process(dev_task))

    qa = QAAgent(bus, memory)
    qa_task = Task(
        title="QA",
        description="Test the feature",
        role="qa",
        context={"dev_result": dev_result, "review_result": {"verdict": "approved"}},
    )
    result = asyncio.run(qa.process(qa_task))

    assert "test_cases" in result
    assert "coverage_pct" in result
    assert "quality_gate_passed" in result
    assert result["test_cases"] > 0
    assert 0 <= result["coverage_pct"] <= 100


# ------------------------------------------------------------------ #
# OrchestratorAgent                                                    #
# ------------------------------------------------------------------ #


def test_orchestrator_generates_task_graph(bus, memory) -> None:
    from agentse.agents.orchestrator import OrchestratorAgent

    orch = OrchestratorAgent(bus, memory)
    task = Task(
        title="User Auth",
        description="Build JWT authentication",
        role="orchestrator",
    )
    result = asyncio.run(orch.process(task))

    assert "tasks" in result
    assert result["task_count"] >= 5  # plan, arch, dev, review, qa

    roles_in_plan = {t["role"] for t in result["tasks"]}
    assert "planner" in roles_in_plan
    assert "architect" in roles_in_plan
    assert "developer" in roles_in_plan
    assert "reviewer" in roles_in_plan
    assert "qa" in roles_in_plan


def test_orchestrator_applies_extra_steps_from_memory(bus, memory) -> None:
    from agentse.agents.orchestrator import OrchestratorAgent

    memory.set_long(
        "process_guidelines",
        {"extra_steps": ["reviewer"], "priority_boost": {}},
    )

    orch = OrchestratorAgent(bus, memory)
    task = Task(
        title="Feature",
        description="Some feature",
        role="orchestrator",
    )
    result = asyncio.run(orch.process(task))
    roles = [t["role"] for t in result["tasks"]]
    # reviewer should appear at least twice (standard + extra)
    assert roles.count("reviewer") >= 2


# ------------------------------------------------------------------ #
# LearnerAgent                                                         #
# ------------------------------------------------------------------ #


def test_learner_generates_trend_report_empty(bus, memory) -> None:
    from agentse.agents.learner import LearnerAgent

    learner = LearnerAgent(bus, memory)
    report = learner.generate_trend_report()
    assert "message" in report or "sprint_count" in report


def test_learner_process_applies_improvements(bus, memory) -> None:
    from agentse.agents.learner import LearnerAgent

    learner = LearnerAgent(bus, memory)
    # Simulate a sprint with high failure rate
    summary = {
        "total": 10,
        "completed": 5,
        "failed": 5,
        "cancelled": 0,
        "avg_task_duration_s": 0.1,
        "agent_metrics": {},
    }
    task = Task(
        title="Retro",
        description=str(summary),
        role="learner",
        sprint_id="sprint_test",
    )
    task.context["sprint_summary"] = summary
    result = asyncio.run(learner.process(task))

    assert "improvements_applied" in result
    assert isinstance(result["improvements"], list)
