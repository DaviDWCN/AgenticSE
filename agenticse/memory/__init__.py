"""Agent Memory Subsystem (AMS).

Three-layer cognitive memory architecture for autonomous Coding Agents:

* Sensory layer  — high-frequency event stream (see :mod:`agenticse.memory.workflows`).
* Working memory — multi-resolution paging context window
  (see :class:`agenticse.memory.working.WorkingMemoryController`).
* Long-term memory — vector (episodic) + graph (topology) hybrid store
  (see :class:`agenticse.memory.long_term.LongTermMemoryMatrix`).

The :class:`AgentMemorySubsystem` facade composes the three layers and the
lifecycle workflows (perception filtering, dynamic awakening, asynchronous
consolidation / reflection).
"""

from agenticse.memory.ams import AgentMemorySubsystem
from agenticse.memory.graph_store import InMemoryGraphStore
from agenticse.memory.long_term import LongTermMemoryMatrix
from agenticse.memory.schemas import (
    Lesson,
    MemorySegments,
    Resolution,
    SensoryEvent,
    WorkingMemoryState,
)
from agenticse.memory.vector_store import InMemoryVectorStore
from agenticse.memory.working import WorkingMemoryController

__all__ = [
    "AgentMemorySubsystem",
    "InMemoryGraphStore",
    "InMemoryVectorStore",
    "Lesson",
    "LongTermMemoryMatrix",
    "MemorySegments",
    "Resolution",
    "SensoryEvent",
    "WorkingMemoryController",
    "WorkingMemoryState",
]
