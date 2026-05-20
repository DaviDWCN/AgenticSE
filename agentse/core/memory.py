"""
Shared in-memory knowledge / memory store.

The MemoryStore provides three layers of memory:

1. **Short-term** — ephemeral key/value store reset each sprint.
2. **Long-term** — persisted across sprints (serialised to JSON on disk).
3. **Episodic** — append-only event log of notable team moments
   (decisions, learnings, retrospective findings).

The long-term and episodic stores back the self-learning engine and allow
the team to *evolve* its own processes over time.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_STORE_PATH = Path(os.environ.get("AGENTSE_STORE_PATH", ".agentse_memory.json"))


class MemoryStore:
    """
    Three-tier memory store for the agent team.

    Parameters
    ----------
    store_path:
        Path to the JSON file used for persistence.  Defaults to
        ``.agentse_memory.json`` in the current working directory (or the
        value of ``AGENTSE_STORE_PATH``).
    """

    def __init__(self, store_path: Path | str | None = None) -> None:
        self._path: Path = Path(store_path) if store_path else _DEFAULT_STORE_PATH
        self._short_term: dict[str, Any] = {}
        self._long_term: dict[str, Any] = {}
        self._episodic: list[dict[str, Any]] = []
        self._log = logger.bind(component="memory_store")
        self._load()

    # ------------------------------------------------------------------
    # Short-term (volatile)
    # ------------------------------------------------------------------

    def set_short(self, key: str, value: Any) -> None:
        self._short_term[key] = value

    def get_short(self, key: str, default: Any = None) -> Any:
        return self._short_term.get(key, default)

    def clear_short_term(self) -> None:
        self._short_term.clear()

    # ------------------------------------------------------------------
    # Long-term (persisted)
    # ------------------------------------------------------------------

    def set_long(self, key: str, value: Any) -> None:
        self._long_term[key] = value
        self._save()

    def get_long(self, key: str, default: Any = None) -> Any:
        return self._long_term.get(key, default)

    def update_long(self, data: dict[str, Any]) -> None:
        self._long_term.update(data)
        self._save()

    # ------------------------------------------------------------------
    # Episodic (append-only log)
    # ------------------------------------------------------------------

    def record_episode(
        self,
        kind: str,
        content: Any,
        agent_id: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Append a notable event to the episodic log."""
        entry: dict[str, Any] = {
            "kind": kind,
            "content": content,
            "agent_id": agent_id,
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._episodic.append(entry)
        self._save()
        self._log.debug("episode_recorded", kind=kind)

    def query_episodes(
        self,
        kind: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent episodes, optionally filtered."""
        results = self._episodic
        if kind:
            results = [e for e in results if e["kind"] == kind]
        if tags:
            results = [
                e for e in results if any(t in e.get("tags", []) for t in tags)
            ]
        return results[-limit:]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            self._log.debug("no_existing_store", path=str(self._path))
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._long_term = data.get("long_term", {})
            self._episodic = data.get("episodic", [])
            self._log.info(
                "store_loaded",
                path=str(self._path),
                long_term_keys=len(self._long_term),
                episodes=len(self._episodic),
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning("store_load_failed", error=str(exc))

    def _save(self) -> None:
        try:
            data = {
                "long_term": self._long_term,
                "episodic": self._episodic,
            }
            self._path.write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning("store_save_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        return {
            "short_term_keys": len(self._short_term),
            "long_term_keys": len(self._long_term),
            "episodic_count": len(self._episodic),
            "store_path": str(self._path),
        }
