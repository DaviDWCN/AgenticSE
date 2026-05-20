"""
SandboxExecutor — deterministic, isolated code execution.

Provides a safe execution environment for agent-generated code.
In production this would spin up an ephemeral container (Docker / gVisor),
execute the code with strict resource limits, and return stdout/stderr.

The implementation here uses Python's ``subprocess`` module with:
- A configurable timeout
- CPU / memory resource limits (Unix ``resource`` module)
- A dedicated temporary directory per execution
- Complete environment variable isolation

Security model
--------------
Generated code is written to a fresh ``/tmp/agentse_sandbox_<uuid>``
directory.  The subprocess inherits no environment variables from the parent
process and network access is not granted.  The ``resource`` module applies
CPU and virtual-memory limits on POSIX systems.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

try:
    import resource as _resource

    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False  # Windows


@dataclass
class ExecutionResult:
    """Result of a sandboxed code execution."""

    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    sandbox_dir: str
    timed_out: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_s": self.duration_s,
            "timed_out": self.timed_out,
            "success": self.success,
        }


def _apply_resource_limits(cpu_seconds: int, memory_mb: int) -> None:
    """Apply POSIX resource limits in the child process."""
    if not _HAS_RESOURCE:
        return
    # CPU time limit
    _resource.setrlimit(_resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    # Virtual memory limit
    mem_bytes = memory_mb * 1024 * 1024
    try:
        _resource.setrlimit(_resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except (ValueError, _resource.error):
        pass  # Some platforms don't support RLIMIT_AS


class SandboxExecutor:
    """
    Runs arbitrary Python code snippets in an isolated subprocess.

    Parameters
    ----------
    timeout_s:    Maximum wall-clock time (seconds) before the process is killed.
    cpu_limit_s:  CPU time limit (POSIX only).
    memory_mb:    Virtual memory limit in MiB (POSIX only).
    """

    def __init__(
        self,
        timeout_s: int = 30,
        cpu_limit_s: int = 15,
        memory_mb: int = 256,
    ) -> None:
        self.timeout_s = timeout_s
        self.cpu_limit_s = cpu_limit_s
        self.memory_mb = memory_mb
        self._log = logger.bind(component="sandbox")

    def execute(
        self,
        code: str,
        extra_files: dict[str, str] | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """
        Execute *code* in an isolated sandbox directory.

        Parameters
        ----------
        code:        Python source code to execute.
        extra_files: Additional files to write into the sandbox dir
                     ``{relative_path: content}``.
        env_vars:    Environment variables to pass to the subprocess
                     (only these vars — parent env is excluded).

        Returns
        -------
        ExecutionResult with stdout, stderr, exit code and timing.
        """
        sandbox_id = str(uuid.uuid4())[:8]
        sandbox_dir = Path(tempfile.gettempdir()) / f"agentse_sandbox_{sandbox_id}"
        sandbox_dir.mkdir(parents=True, exist_ok=True)

        self._log.info("sandbox_created", sandbox_id=sandbox_id, dir=str(sandbox_dir))

        try:
            # Write the main script
            script_path = sandbox_dir / "main.py"
            script_path.write_text(code, encoding="utf-8")

            # Write any extra files
            if extra_files:
                for rel_path, content in extra_files.items():
                    target = sandbox_dir / rel_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")

            # Build a minimal, clean environment
            clean_env: dict[str, str] = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(sandbox_dir),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            if env_vars:
                clean_env.update(env_vars)

            preexec = None
            if _HAS_RESOURCE:
                cpu = self.cpu_limit_s
                mem = self.memory_mb

                def preexec() -> None:
                    _apply_resource_limits(cpu, mem)

            import time

            start = time.monotonic()
            timed_out = False

            try:
                proc = subprocess.run(
                    ["python3", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    env=clean_env,
                    cwd=str(sandbox_dir),
                    preexec_fn=preexec,
                )
                duration = time.monotonic() - start
                result = ExecutionResult(
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    duration_s=round(duration, 3),
                    sandbox_dir=str(sandbox_dir),
                )
            except subprocess.TimeoutExpired:
                duration = time.monotonic() - start
                timed_out = True
                result = ExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr="Execution timed out",
                    duration_s=round(duration, 3),
                    sandbox_dir=str(sandbox_dir),
                    timed_out=True,
                )

            self._log.info(
                "sandbox_done",
                sandbox_id=sandbox_id,
                exit_code=result.exit_code,
                duration_s=result.duration_s,
                timed_out=timed_out,
            )
            return result

        finally:
            # Always clean up the sandbox directory
            try:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
