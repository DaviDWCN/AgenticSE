"""High-level facade tying the three AMS layers together."""

from __future__ import annotations

from typing import Iterable, List, Optional

from agenticse.memory.long_term import LongTermMemoryMatrix
from agenticse.memory.schemas import (
    AwakeningContext,
    Lesson,
    Resolution,
    SensoryEvent,
    WorkingMemoryState,
)
from agenticse.memory.working import WorkingMemoryController
from agenticse.memory.workflows import (
    PerceptionPolicy,
    awaken_for_task,
    consolidate_session,
    ingest_events,
)


class AgentMemorySubsystem:
    """One-stop entry point for orchestrators.

    Typical lifecycle::

        ams = AgentMemorySubsystem()
        ams.start_task("Fix NPE in OrderService.checkout()")
        ams.ingest(events)           # streamed from IDE / terminal
        ctx = ams.awaken_prompt()    # inject into System Prompt
        ...
        ams.record_lesson(Lesson("Always null-check the cart before tax calc",
                                  related_classes=["OrderService"]))
        ams.finish_task()
    """

    def __init__(
        self,
        long_term: Optional[LongTermMemoryMatrix] = None,
        token_budget: int = 128_000,
        perception_policy: Optional[PerceptionPolicy] = None,
    ) -> None:
        self.ltm = long_term or LongTermMemoryMatrix()
        self._default_budget = token_budget
        self._policy = perception_policy
        self._controller: Optional[WorkingMemoryController] = None
        self._last_task_input: str = ""

    # ------------------------------------------------------------------ #
    # Task lifecycle
    # ------------------------------------------------------------------ #
    def start_task(
        self,
        task_input: str,
        active_files: Iterable[str] = (),
        token_budget: Optional[int] = None,
    ) -> WorkingMemoryController:
        """Open a fresh working-memory session for a new task."""

        state = WorkingMemoryState(
            token_budget=token_budget or self._default_budget,
            active_file_focus=list(active_files),
        )
        self._controller = WorkingMemoryController(state=state)
        self._last_task_input = task_input
        self._controller.add_message("user", task_input)
        return self._controller

    @property
    def controller(self) -> WorkingMemoryController:
        if self._controller is None:
            raise RuntimeError("No active task — call start_task() first")
        return self._controller

    @property
    def state(self) -> WorkingMemoryState:
        return self.controller.state

    # ------------------------------------------------------------------ #
    # Ingestion + recall
    # ------------------------------------------------------------------ #
    def ingest(self, events: Iterable[SensoryEvent]) -> int:
        return ingest_events(self.controller, events, self._policy)

    def remember(self, text: str, resolution: Resolution = Resolution.HIGH) -> None:
        self.controller.add(text, resolution=resolution)

    def awaken(
        self,
        task_input: Optional[str] = None,
        explicit_anchors: Iterable[str] = (),
        top_k_lessons: int = 5,
        upstream_depth: int = 2,
        downstream_depth: int = 1,
    ) -> AwakeningContext:
        """Run the dynamic awakening workflow against the LTM."""

        prompt = task_input or self._last_task_input
        return awaken_for_task(
            prompt,
            self.ltm,
            explicit_anchors=explicit_anchors,
            top_k_lessons=top_k_lessons,
            upstream_depth=upstream_depth,
            downstream_depth=downstream_depth,
        )

    def awaken_prompt(self, **kwargs) -> str:
        """Convenience: return the awakening context already rendered to text."""

        return self.awaken(**kwargs).render_prompt()

    # ------------------------------------------------------------------ #
    # LTM writes
    # ------------------------------------------------------------------ #
    def record_lesson(self, lesson: Lesson) -> str:
        return self.ltm.record_lesson(lesson)

    def record_call(self, caller: str, callee: str) -> None:
        self.ltm.record_call(caller, callee)

    def record_dependency(self, source_class: str, target_class: str) -> None:
        self.ltm.record_dependency(source_class, target_class)

    # ------------------------------------------------------------------ #
    # Reflection
    # ------------------------------------------------------------------ #
    def finish_task(self, lessons: Iterable[Lesson] = ()) -> List[str]:
        """Consolidate the active session into the LTM and close it."""

        if self._controller is None:
            return []
        stored = consolidate_session(self._controller.state, self.ltm, lessons)
        self._controller = None
        self._last_task_input = ""
        return stored
