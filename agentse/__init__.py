"""
AgenticSE — Autonomous Multi-Agent Software Engineering Team

This package provides an event-driven, self-learning multi-agent framework
for end-to-end software engineering automation.
"""

from agentse.core.agent import Agent, AgentRole, AgentStatus
from agentse.core.event_bus import EventBus, Event, EventType
from agentse.core.task import Task, TaskStatus, TaskPriority
from agentse.core.memory import MemoryStore
from agentse.core.workflow import WorkflowEngine

__all__ = [
    "Agent",
    "AgentRole",
    "AgentStatus",
    "EventBus",
    "Event",
    "EventType",
    "Task",
    "TaskStatus",
    "TaskPriority",
    "MemoryStore",
    "WorkflowEngine",
]

__version__ = "0.1.0"
