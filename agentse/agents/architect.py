"""
ArchitectAgent — system design and technology selection.

Produces an architecture document that specifies components, interfaces,
data models, and technology choices for the feature being built.
"""

from __future__ import annotations

from typing import Any

import structlog

from agentse.core.agent import Agent, AgentRole
from agentse.core.event_bus import EventBus
from agentse.core.memory import MemoryStore
from agentse.core.task import Task

logger = structlog.get_logger(__name__)


class ArchitectAgent(Agent):
    """Designs system architecture for a given requirement."""

    def __init__(self, event_bus: EventBus, memory: MemoryStore) -> None:
        super().__init__(AgentRole.ARCHITECT, event_bus, memory)
        self._log = logger.bind(agent="architect")

    async def process(self, task: Task) -> dict[str, Any]:
        requirement = task.description
        self._log.info("designing_architecture", task_id=task.task_id[:8])

        # Retrieve any established tech-stack preferences
        tech_stack: dict[str, str] = self.memory.get_long(
            "preferred_tech_stack",
            {
                "language": "Python",
                "framework": "FastAPI",
                "database": "PostgreSQL",
                "queue": "Redis Streams",
                "containerisation": "Docker + Kubernetes",
            },
        )

        components = self._derive_components(requirement, tech_stack)
        interfaces = self._define_interfaces(components)
        data_models = self._design_data_models(requirement)

        architecture = {
            "tech_stack": tech_stack,
            "components": components,
            "interfaces": interfaces,
            "data_models": data_models,
            "patterns": [
                "Event-driven architecture",
                "CQRS for read/write separation",
                "Repository pattern for data access",
                "Circuit-breaker for external dependencies",
            ],
            "non_functional": {
                "availability": "99.9%",
                "latency_p99_ms": 200,
                "scalability": "Horizontal via stateless services",
            },
        }

        self._log.info(
            "architecture_designed",
            components=len(components),
        )

        self.memory.record_episode(
            kind="architecture_designed",
            content={
                "requirement_snippet": requirement[:100],
                "component_count": len(components),
                "tech_stack": tech_stack,
            },
            agent_id=self.agent_id,
            tags=["architecture", task.sprint_id or ""],
        )

        return architecture

    # ------------------------------------------------------------------

    def _derive_components(
        self, requirement: str, tech_stack: dict[str, str]
    ) -> list[dict[str, str]]:
        components = [
            {
                "name": "API Gateway",
                "type": "service",
                "tech": tech_stack.get("framework", "FastAPI"),
                "responsibility": "Entry point; routing, auth, rate-limiting",
            },
            {
                "name": "Business Logic Service",
                "type": "service",
                "tech": tech_stack.get("language", "Python"),
                "responsibility": "Core domain logic",
            },
            {
                "name": "Data Store",
                "type": "database",
                "tech": tech_stack.get("database", "PostgreSQL"),
                "responsibility": "Persistent storage",
            },
            {
                "name": "Event Bus",
                "type": "infrastructure",
                "tech": tech_stack.get("queue", "Redis Streams"),
                "responsibility": "Async inter-service communication",
            },
        ]
        req_lower = requirement.lower()
        if any(w in req_lower for w in ["cache", "fast", "performance"]):
            components.append(
                {
                    "name": "Cache Layer",
                    "type": "infrastructure",
                    "tech": "Redis",
                    "responsibility": "Low-latency read cache",
                }
            )
        if any(w in req_lower for w in ["file", "upload", "storage", "s3"]):
            components.append(
                {
                    "name": "Object Storage",
                    "type": "infrastructure",
                    "tech": "S3-compatible",
                    "responsibility": "Binary file storage",
                }
            )
        return components

    def _define_interfaces(
        self, components: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        return [
            {
                "from": "API Gateway",
                "to": "Business Logic Service",
                "protocol": "HTTP/2 (gRPC)",
                "contract": "Protobuf",
            },
            {
                "from": "Business Logic Service",
                "to": "Data Store",
                "protocol": "TCP",
                "contract": "SQL / ORM",
            },
            {
                "from": "Business Logic Service",
                "to": "Event Bus",
                "protocol": "TCP",
                "contract": "JSON events",
            },
        ]

    def _design_data_models(self, requirement: str) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = [
            {
                "name": "Entity",
                "fields": ["id: UUID", "created_at: datetime", "updated_at: datetime"],
                "indexes": ["PRIMARY KEY (id)", "INDEX (created_at)"],
            }
        ]
        req_lower = requirement.lower()
        if any(w in req_lower for w in ["user", "auth", "login"]):
            models.append(
                {
                    "name": "User",
                    "fields": [
                        "id: UUID",
                        "email: str",
                        "hashed_password: str",
                        "created_at: datetime",
                    ],
                    "indexes": ["PRIMARY KEY (id)", "UNIQUE (email)"],
                }
            )
        return models
