"""
Tests for the SandboxExecutor.
"""

import pytest

from agentse.sandbox.executor import SandboxExecutor, ExecutionResult


@pytest.fixture
def sandbox() -> SandboxExecutor:
    return SandboxExecutor(timeout_s=10, cpu_limit_s=5, memory_mb=128)


def test_successful_execution(sandbox: SandboxExecutor) -> None:
    result = sandbox.execute("print('hello, agentse')")
    assert result.success
    assert result.exit_code == 0
    assert "hello, agentse" in result.stdout
    assert result.duration_s >= 0


def test_failed_execution_non_zero_exit(sandbox: SandboxExecutor) -> None:
    result = sandbox.execute("import sys; sys.exit(1)")
    assert not result.success
    assert result.exit_code == 1


def test_syntax_error_produces_non_zero_exit(sandbox: SandboxExecutor) -> None:
    result = sandbox.execute("def foo(")
    assert not result.success
    assert result.exit_code != 0
    assert result.stderr  # should have error output


def test_timeout_handling() -> None:
    slow_sandbox = SandboxExecutor(timeout_s=1)
    result = slow_sandbox.execute("import time; time.sleep(60)")
    assert result.timed_out
    assert not result.success


def test_extra_files(sandbox: SandboxExecutor) -> None:
    extra = {"helper.py": "VALUE = 'from_helper'"}
    code = "from helper import VALUE; print(VALUE)"
    result = sandbox.execute(code, extra_files=extra)
    assert result.success
    assert "from_helper" in result.stdout


def test_isolated_environment(sandbox: SandboxExecutor) -> None:
    """The sandbox should not inherit parent environment vars."""
    import os
    os.environ["AGENTSE_SECRET"] = "super_secret_value"
    result = sandbox.execute(
        "import os; print(os.environ.get('AGENTSE_SECRET', 'NOT_SET'))"
    )
    # Should NOT be able to see the parent env var
    assert "super_secret_value" not in result.stdout


def test_execution_result_to_dict(sandbox: SandboxExecutor) -> None:
    result = sandbox.execute("x = 1 + 1")
    d = result.to_dict()
    for key in ["exit_code", "stdout", "stderr", "duration_s", "timed_out", "success"]:
        assert key in d
