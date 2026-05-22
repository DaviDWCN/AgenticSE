"""Memory lifecycle workflows — perception filter, awakening, consolidation.

Implements §4 of the AMS spec. Workflows are pure functions over the
working / long-term memory primitives so they can be re-used by any
orchestrator (LangGraph, custom event loop, ...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set

from agenticse.memory.long_term import LongTermMemoryMatrix
from agenticse.memory.schemas import (
    AwakeningContext,
    Lesson,
    Resolution,
    SensoryEvent,
    WorkingMemoryState,
)
from agenticse.memory.working import WorkingMemoryController

# Class-name-shaped tokens used as anchors during awakening.
_ANCHOR_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\b")
_PATH_PATTERN = re.compile(r"[\w./\\-]+\.(?:py|java|ts|tsx|js|go|rs|cpp|c|h|hpp|kt)")


# --------------------------------------------------------------------------- #
# 4.0  Perception filter
# --------------------------------------------------------------------------- #
@dataclass
class PerceptionPolicy:
    """Configuration for :func:`perception_filter`.

    * ``allowed_sources`` — drop events whose ``source`` is not in this set.
    * ``noisy_substrings`` — drop events whose payload contains any of these.
    * ``min_payload_chars`` — drop trivially short payloads (e.g. blank ticks).
    """

    allowed_sources: Set[str] = None  # type: ignore[assignment]
    noisy_substrings: Set[str] = None  # type: ignore[assignment]
    min_payload_chars: int = 1

    def __post_init__(self) -> None:
        if self.allowed_sources is None:
            self.allowed_sources = {"ide", "terminal", "user", "agent"}
        if self.noisy_substrings is None:
            self.noisy_substrings = {"DEBUG heartbeat", "keepalive"}


def perception_filter(
    events: Iterable[SensoryEvent],
    policy: Optional[PerceptionPolicy] = None,
) -> List[SensoryEvent]:
    """Strip noisy / irrelevant events from a raw sensory stream."""

    pol = policy or PerceptionPolicy()
    kept: List[SensoryEvent] = []
    for ev in events:
        if ev.source not in pol.allowed_sources:
            continue
        if not ev.payload or len(ev.payload) < pol.min_payload_chars:
            continue
        if any(noise in ev.payload for noise in pol.noisy_substrings):
            continue
        kept.append(ev)
    return kept


# --------------------------------------------------------------------------- #
# 4.1  Dynamic awakening
# --------------------------------------------------------------------------- #
def extract_anchors(text: str) -> List[str]:
    """Pull file paths and class-name tokens from free-form text."""

    anchors: List[str] = []
    seen: Set[str] = set()
    for match in _PATH_PATTERN.findall(text):
        if match not in seen:
            seen.add(match)
            anchors.append(match)
    for match in _ANCHOR_PATTERN.findall(text):
        if match not in seen:
            seen.add(match)
            anchors.append(match)
    return anchors


def awaken_for_task(
    task_input: str,
    ltm: LongTermMemoryMatrix,
    explicit_anchors: Iterable[str] = (),
    top_k_lessons: int = 5,
    upstream_depth: int = 2,
    downstream_depth: int = 1,
) -> AwakeningContext:
    """Run the dynamic awakening workflow described in §4.1.

    Extracts anchor symbols from ``task_input`` (or uses ``explicit_anchors``
    when provided), then fans out:

    * Vector search over the lesson library (avoid-the-pit guide).
    * 2-hop upstream / 1-hop downstream graph expansion per anchor.
    """

    anchors = list(explicit_anchors) or extract_anchors(task_input)
    return ltm.awaken(
        query=task_input,
        anchors=anchors,
        top_k_lessons=top_k_lessons,
        upstream_depth=upstream_depth,
        downstream_depth=downstream_depth,
    )


# --------------------------------------------------------------------------- #
# 4.2  Asynchronous consolidation / reflection
# --------------------------------------------------------------------------- #
def consolidate_session(
    state: WorkingMemoryState,
    ltm: LongTermMemoryMatrix,
    lessons: Iterable[Lesson] = (),
) -> List[str]:
    """End-of-task reflection: persist lessons + summarised trajectory.

    Returns the list of lesson ids that were stored. The working-memory
    ``low_res`` trail is also flushed into the vector store with a
    ``trajectory`` tag so future awakenings can surface it.
    """

    stored: List[str] = []
    for lesson in lessons:
        stored.append(ltm.record_lesson(lesson))

    # Persist the abstract trajectory so we can revisit "what did the agent
    # already try" in a later session.
    for line in state.memory_segments.low_res:
        if not line.strip():
            continue
        ltm.vector.upsert(
            line,
            metadata={"task_id": state.task_id, "kind": "trajectory"},
            tags=["trajectory"],
        )
    return stored


# --------------------------------------------------------------------------- #
# Convenience: end-to-end ingestion
# --------------------------------------------------------------------------- #
def ingest_events(
    controller: WorkingMemoryController,
    events: Iterable[SensoryEvent],
    policy: Optional[PerceptionPolicy] = None,
) -> int:
    """Filter then promote a batch of sensory events into working memory.

    Returns the number of events that survived the perception filter.
    """

    kept = perception_filter(events, policy)
    for ev in kept:
        controller.ingest_event(ev)
    return len(kept)


__all__ = [
    "PerceptionPolicy",
    "perception_filter",
    "extract_anchors",
    "awaken_for_task",
    "consolidate_session",
    "ingest_events",
]
