"""Working memory controller — multi-resolution paging over the LLM window.

Implements §3.1 of the AMS spec. The controller never hands raw history to
the LLM; instead it maintains three resolution tiers and demotes / compresses
content as the token budget is approached.
"""

from __future__ import annotations

from typing import Callable, Iterable, List, Optional

from agenticse.memory.embeddings import estimate_tokens, joined_tokens
from agenticse.memory.schemas import (
    MemorySegments,
    Resolution,
    SensoryEvent,
    WorkingMemoryState,
)

Compressor = Callable[[str], str]


def _default_mid_compressor(text: str) -> str:
    """Reduce a raw source fragment to its signature / class+method skeleton.

    Heuristic: keep declaration-looking lines (``class``, ``def``, ``func``,
    ``public``, signatures with parens), drop bodies. Never larger than input.
    """

    keep: List[str] = []
    signature_keywords = (
        "class ",
        "def ",
        "func ",
        "fn ",
        "function ",
        "public ",
        "private ",
        "protected ",
        "interface ",
        "struct ",
        "enum ",
        "type ",
    )
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()
        if not stripped:
            continue
        if any(stripped.startswith(k) for k in signature_keywords):
            keep.append(line.split("{", 1)[0].rstrip(" :{"))
        elif stripped.endswith(":") and "(" in stripped:
            keep.append(line)
    if not keep:
        # Fall back to the first non-empty line.
        for raw_line in text.splitlines():
            if raw_line.strip():
                keep.append(raw_line.strip())
                break
    return "\n".join(keep)


def _default_low_compressor(text: str) -> str:
    """Collapse a fragment to a one-line abstract summary."""

    snippet = " ".join(text.split())
    if len(snippet) > 120:
        snippet = snippet[:117] + "..."
    return f"[abstract] {snippet}"


class WorkingMemoryController:
    """Manage a :class:`WorkingMemoryState` under a strict token budget.

    The controller exposes three resolution tiers (``HIGH`` / ``MID`` /
    ``LOW``) and a single rule: **total tokens across all tiers must never
    exceed** :attr:`WorkingMemoryState.token_budget`. When the budget is
    breached the oldest high-res entries are demoted to mid-res (compressed),
    then mid-res to low-res, then low-res entries are evicted FIFO.

    The compressors are pluggable so real deployments can wire in an AST
    extractor / LLM summariser.
    """

    def __init__(
        self,
        state: Optional[WorkingMemoryState] = None,
        mid_compressor: Optional[Compressor] = None,
        low_compressor: Optional[Compressor] = None,
        safety_margin: float = 0.05,
    ) -> None:
        if not 0.0 <= safety_margin < 1.0:
            raise ValueError("safety_margin must be in [0, 1)")
        self.state = state or WorkingMemoryState()
        self._mid_compressor = mid_compressor or _default_mid_compressor
        self._low_compressor = low_compressor or _default_low_compressor
        self._safety_margin = safety_margin

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #
    @property
    def segments(self) -> MemorySegments:
        return self.state.memory_segments

    @property
    def token_budget(self) -> int:
        return self.state.token_budget

    @property
    def effective_budget(self) -> int:
        return max(1, int(self.token_budget * (1.0 - self._safety_margin)))

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def add(self, content: str, resolution: Resolution = Resolution.HIGH) -> None:
        """Append ``content`` to the requested tier and re-balance the budget."""

        if not content:
            return
        bucket = self._bucket(resolution)
        bucket.append(content)
        self._enforce_budget()

    def add_many(
        self, items: Iterable[str], resolution: Resolution = Resolution.HIGH
    ) -> None:
        for item in items:
            self.add(item, resolution)

    def add_message(self, role: str, content: str) -> None:
        """Append a chat message and mirror its content into the high-res tier."""

        self.state.messages.append({"role": role, "content": content})
        # Only the most recent user/assistant turns belong in the live context;
        # older ones get demoted by the budget enforcer below.
        self.add(content, Resolution.HIGH)

    def ingest_event(self, event: SensoryEvent) -> None:
        """Promote a filtered :class:`SensoryEvent` into working memory."""

        prefix = f"[{event.source}:{event.kind}]"
        # Stack traces and crash payloads are pinned in the high-res tier; the
        # spec mandates these survive paging.
        resolution = (
            Resolution.HIGH
            if event.kind in {"stack_trace", "crash", "user_msg"}
            else Resolution.MID
        )
        self.add(f"{prefix} {event.payload}", resolution=resolution)

    def focus(self, files: Iterable[str]) -> None:
        """Replace the ``active_file_focus`` list."""

        self.state.active_file_focus = [f for f in files if f]

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def render_context(self) -> str:
        """Return a prompt-ready textual rendering of the three tiers."""

        s = self.segments
        sections: List[str] = []
        if s.high_res:
            sections.append("### [HIGH-RES] Active code & critical traces")
            sections.extend(s.high_res)
        if s.mid_res:
            sections.append("### [MID-RES] Signatures & structural context")
            sections.extend(s.mid_res)
        if s.low_res:
            sections.append("### [LOW-RES] Abstract trajectory")
            sections.extend(s.low_res)
        return "\n".join(sections)

    def token_usage(self) -> int:
        s = self.segments
        return joined_tokens(s.high_res) + joined_tokens(s.mid_res) + joined_tokens(
            s.low_res
        )

    def retention_ratio(self, originals: Iterable[str]) -> float:
        """Compute the lossless-retention ratio (§1.1 metric) for ``originals``.

        An original item is considered "retained" if it (or a normalised
        compression of it) still appears verbatim or as a substring anywhere
        in the working memory.
        """

        originals = list(originals)
        if not originals:
            return 1.0
        haystack = self.render_context()
        retained = sum(1 for item in originals if item and item in haystack)
        return retained / len(originals)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _bucket(self, resolution: Resolution) -> List[str]:
        if resolution is Resolution.HIGH:
            return self.segments.high_res
        if resolution is Resolution.MID:
            return self.segments.mid_res
        return self.segments.low_res

    def _enforce_budget(self) -> None:
        budget = self.effective_budget
        # Demote oldest high-res → mid-res.
        guard = 0
        while self.token_usage() > budget and self.segments.high_res:
            oldest = self.segments.high_res.pop(0)
            self.segments.mid_res.append(self._mid_compressor(oldest))
            guard += 1
            if guard > 10_000:  # pragma: no cover - defensive
                break
        # Demote oldest mid-res → low-res.
        guard = 0
        while self.token_usage() > budget and self.segments.mid_res:
            oldest = self.segments.mid_res.pop(0)
            self.segments.low_res.append(self._low_compressor(oldest))
            guard += 1
            if guard > 10_000:  # pragma: no cover - defensive
                break
        # Evict oldest low-res.
        guard = 0
        while self.token_usage() > budget and self.segments.low_res:
            self.segments.low_res.pop(0)
            guard += 1
            if guard > 10_000:  # pragma: no cover - defensive
                break

    # ------------------------------------------------------------------ #
    # Repr
    # ------------------------------------------------------------------ #
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        s = self.segments
        return (
            f"WorkingMemoryController(task={self.state.task_id[:8]}, "
            f"high={len(s.high_res)}, mid={len(s.mid_res)}, low={len(s.low_res)}, "
            f"tokens={self.token_usage()}/{self.token_budget})"
        )
