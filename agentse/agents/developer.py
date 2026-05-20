"""
DeveloperAgent — code generation and implementation.

Produces implementation artefacts: module structure, pseudocode / skeleton
code, and a list of files to be created.  In a production deployment this
agent would call an LLM code-generation endpoint and then pass generated code
to the sandbox for execution and validation.
"""

from __future__ import annotations

from typing import Any

import structlog

from agentse.core.agent import Agent, AgentRole
from agentse.core.event_bus import EventBus
from agentse.core.memory import MemoryStore
from agentse.core.task import Task

logger = structlog.get_logger(__name__)


class DeveloperAgent(Agent):
    """Generates implementation artefacts for a feature."""

    def __init__(self, event_bus: EventBus, memory: MemoryStore) -> None:
        super().__init__(AgentRole.DEVELOPER, event_bus, memory)
        self._log = logger.bind(agent="developer")

    async def process(self, task: Task) -> dict[str, Any]:
        requirement = task.description
        self._log.info("implementing_feature", task_id=task.task_id[:8])

        # Retrieve coding standards from memory
        coding_standards: dict[str, Any] = self.memory.get_long(
            "coding_standards",
            {
                "style": "PEP 8",
                "max_line_length": 88,
                "type_hints": True,
                "docstrings": "Google style",
                "test_coverage_threshold": 80,
            },
        )

        modules = self._plan_modules(requirement)
        code_artefacts = self._generate_skeletons(modules, coding_standards)

        result = {
            "modules": modules,
            "artefacts": code_artefacts,
            "coding_standards_applied": coding_standards,
            "implementation_notes": [
                "All public functions have type annotations",
                "Each module has a corresponding test file",
                "No hardcoded secrets — use environment variables",
                "Dependency injection used for all external services",
            ],
        }

        self._log.info("implementation_complete", modules=len(modules))

        self.memory.record_episode(
            kind="implementation_created",
            content={
                "requirement_snippet": requirement[:100],
                "module_count": len(modules),
            },
            agent_id=self.agent_id,
            tags=["development", task.sprint_id or ""],
        )

        return result

    # ------------------------------------------------------------------

    def _plan_modules(self, requirement: str) -> list[dict[str, str]]:
        modules = [
            {
                "name": "api",
                "path": "src/api/routes.py",
                "description": "HTTP route handlers",
            },
            {
                "name": "service",
                "path": "src/service/core.py",
                "description": "Business logic layer",
            },
            {
                "name": "repository",
                "path": "src/repository/db.py",
                "description": "Database access layer",
            },
            {
                "name": "models",
                "path": "src/models/entities.py",
                "description": "Pydantic data models",
            },
        ]
        req_lower = requirement.lower()
        if any(w in req_lower for w in ["event", "queue", "async", "message"]):
            modules.append(
                {
                    "name": "events",
                    "path": "src/events/handlers.py",
                    "description": "Event producers and consumers",
                }
            )
        if any(w in req_lower for w in ["auth", "token", "jwt", "oauth"]):
            modules.append(
                {
                    "name": "auth",
                    "path": "src/auth/middleware.py",
                    "description": "Authentication middleware",
                }
            )
        return modules

    def _generate_skeletons(
        self,
        modules: list[dict[str, str]],
        standards: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Generate skeleton code for each module."""
        artefacts = []
        for mod in modules:
            skeleton = self._module_skeleton(
                mod["name"],
                mod["description"],
                use_type_hints=standards.get("type_hints", True),
            )
            artefacts.append(
                {
                    "path": mod["path"],
                    "content": skeleton,
                    "type": "python",
                }
            )
        return artefacts

    def _module_skeleton(
        self, name: str, description: str, use_type_hints: bool = True
    ) -> str:
        type_str = " -> None" if use_type_hints else ""
        return (
            f'"""\n{description}\n"""\n\n'
            f"from __future__ import annotations\n\n"
            f"import structlog\n\n"
            f"logger = structlog.get_logger(__name__)\n\n\n"
            f"class {name.capitalize()}:\n"
            f'    """Main class for the {name} module."""\n\n'
            f"    def __init__(self){type_str}:\n"
            f"        self._log = logger.bind(module={name!r})\n\n"
            f"    # TODO: implement methods\n"
        )
