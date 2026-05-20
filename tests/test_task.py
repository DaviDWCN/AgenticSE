"""
Tests for Task lifecycle management.
"""

import pytest

from agentse.core.task import Task, TaskPriority, TaskStatus


def test_task_defaults() -> None:
    task = Task(title="My Task", description="Do something", role="developer")
    assert task.status == TaskStatus.PENDING
    assert task.attempts == 0
    assert task.depends_on == []
    assert task.context == {}
    assert task.result == {}
    assert task.task_id  # non-empty


def test_task_mark_started() -> None:
    task = Task(title="T", description="D", role="developer")
    task.mark_started()
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.attempts == 1
    assert task.started_at is not None


def test_task_mark_completed() -> None:
    task = Task(title="T", description="D", role="developer")
    task.mark_started()
    task.mark_completed({"output": "ok"})
    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"output": "ok"}
    assert task.completed_at is not None
    assert task.duration_s is not None
    assert task.duration_s >= 0


def test_task_mark_failed_retryable() -> None:
    task = Task(title="T", description="D", role="developer", max_attempts=3)
    task.mark_started()
    task.mark_failed("timeout")
    # Not exhausted yet — should be pending (retryable)
    assert task.status == TaskStatus.PENDING
    assert task.error == "timeout"


def test_task_mark_failed_exhausted() -> None:
    task = Task(title="T", description="D", role="developer", max_attempts=1)
    task.mark_started()
    task.mark_failed("error")
    assert task.status == TaskStatus.FAILED


def test_task_is_ready() -> None:
    dep_id = "dep-1"
    task = Task(title="T", description="D", role="qa", depends_on=[dep_id])
    assert not task.is_ready(set())
    assert not task.is_ready({"other-id"})
    assert task.is_ready({dep_id})


def test_task_is_ready_no_deps() -> None:
    task = Task(title="T", description="D", role="qa")
    assert task.is_ready(set())


def test_task_to_dict_keys() -> None:
    task = Task(
        title="Build feature",
        description="Long description",
        role="developer",
        priority=TaskPriority.HIGH,
        depends_on=["abc"],
        context={"key": "value"},
    )
    d = task.to_dict()
    for key in [
        "task_id",
        "title",
        "description",
        "role",
        "priority",
        "status",
        "depends_on",
        "context",
        "result",
        "error",
        "attempts",
        "created_at",
    ]:
        assert key in d, f"Missing key: {key}"


def test_task_priority_values() -> None:
    assert TaskPriority.LOW < TaskPriority.NORMAL < TaskPriority.HIGH < TaskPriority.CRITICAL
