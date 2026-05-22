"""Typed schemas used across the AMS layers.

These dataclasses are deliberately serialisable to JSON so the same state
object can be ferried across LangGraph nodes, persisted to disk, or shipped
to remote inference workers.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Resolution(str, Enum):
    """Multi-resolution paging tiers for the working memory."""

    HIGH = "high_res"
    MID = "mid_res"
    LOW = "low_res"


@dataclass
class MemorySegments:
    """Three-tier paged buffer that backs the LLM context window."""

    high_res: List[str] = field(default_factory=list)
    mid_res: List[str] = field(default_factory=list)
    low_res: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, List[str]]:
        return {
            Resolution.HIGH.value: list(self.high_res),
            Resolution.MID.value: list(self.mid_res),
            Resolution.LOW.value: list(self.low_res),
        }


@dataclass
class WorkingMemoryState:
    """Per-task working memory state, mirrors the LangGraph State schema."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    active_file_focus: List[str] = field(default_factory=list)
    token_budget: int = 128_000
    memory_segments: MemorySegments = field(default_factory=MemorySegments)
    messages: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "active_file_focus": list(self.active_file_focus),
            "token_budget": self.token_budget,
            "memory_segments": self.memory_segments.to_dict(),
            "messages": list(self.messages),
            "metadata": dict(self.metadata),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass
class SensoryEvent:
    """Raw event coming from the IDE / terminal / user input bus."""

    source: str  # "ide", "terminal", "user", "agent", ...
    payload: str
    kind: str = "raw"  # "ast_change", "stdout", "stack_trace", "user_msg", ...
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Lesson:
    """A reflection / debugging lesson destined for the LTM."""

    content: str
    tags: List[str] = field(default_factory=list)
    related_classes: List[str] = field(default_factory=list)
    severity: str = "info"  # info | warning | critical
    timestamp: float = field(default_factory=time.time)
    lesson_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedMemory:
    """A single retrieval hit returned by the LTM."""

    content: str
    score: float
    source: str  # "vector" | "graph"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AwakeningContext:
    """Output of the dynamic awakening workflow."""

    lessons: List[RetrievedMemory] = field(default_factory=list)
    topology: List[RetrievedMemory] = field(default_factory=list)

    def render_prompt(self) -> str:
        """Render the awakening context for direct injection into a System Prompt."""

        lines: List[str] = []
        if self.lessons:
            lines.append("## Lessons learned from prior tasks")
            for m in self.lessons:
                lines.append(f"- ({m.score:.2f}) {m.content}")
        if self.topology:
            lines.append("## Relevant code topology")
            for m in self.topology:
                lines.append(f"- {m.content}")
        return "\n".join(lines)


def _ensure_segments(obj: Any) -> MemorySegments:
    if isinstance(obj, MemorySegments):
        return obj
    if isinstance(obj, dict):
        return MemorySegments(
            high_res=list(obj.get("high_res", [])),
            mid_res=list(obj.get("mid_res", [])),
            low_res=list(obj.get("low_res", [])),
        )
    raise TypeError(f"Cannot coerce {type(obj)!r} to MemorySegments")


def state_from_dict(data: Dict[str, Any]) -> WorkingMemoryState:
    """Rehydrate a :class:`WorkingMemoryState` from a plain ``dict``."""

    return WorkingMemoryState(
        task_id=data.get("task_id", str(uuid.uuid4())),
        active_file_focus=list(data.get("active_file_focus", [])),
        token_budget=int(data.get("token_budget", 128_000)),
        memory_segments=_ensure_segments(data.get("memory_segments", {})),
        messages=list(data.get("messages", [])),
        metadata=dict(data.get("metadata", {})),
    )
