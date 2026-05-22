"""Command line interface for agent-friendly AMS workflows.

The CLI stores a JSON snapshot after every mutating command so coding agents
can call it repeatedly from short-lived shell processes while preserving long-
term lessons, graph topology and the active working-memory session.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from agenticse.memory import AgentMemorySubsystem
from agenticse.memory.persistence import (
    backup_path,
    load_snapshot,
    save_snapshot,
    snapshot_lock,
)
from agenticse.memory.schemas import Lesson, Resolution, SensoryEvent


DEFAULT_MAX_PAYLOAD_BYTES = 1_000_000


def parse_eval_case(raw: str) -> Tuple[str, List[str], List[str]]:
    """Parse ``query|term1,term2|anchor1,anchor2`` eval case syntax."""

    parts = [part.strip() for part in raw.split("|", 2)]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(
            "eval cases must use: query|expected term,another term|optional anchor"
        )
    expected_terms = [term.strip() for term in parts[1].split(",") if term.strip()]
    anchors = []
    if len(parts) == 3:
        anchors = [anchor.strip() for anchor in parts[2].split(",") if anchor.strip()]
    if not expected_terms:
        raise ValueError("eval case must include at least one expected term")
    return parts[0], expected_terms, anchors


def evaluate_cases(
    ams: AgentMemorySubsystem,
    raw_cases: Iterable[str],
    top_k_lessons: int,
    upstream_depth: int,
    downstream_depth: int,
) -> Tuple[int, int]:
    """Run golden-query retrieval checks and print a compact report."""

    cases = [parse_eval_case(raw) for raw in raw_cases]
    if not cases:
        raise ValueError("at least one --case is required")

    passed = 0
    for index, (query, expected_terms, anchors) in enumerate(cases, start=1):
        rendered = ams.awaken(
            task_input=query,
            explicit_anchors=anchors,
            top_k_lessons=top_k_lessons,
            upstream_depth=upstream_depth,
            downstream_depth=downstream_depth,
        ).render_prompt()
        haystack = rendered.lower()
        missing = [term for term in expected_terms if term.lower() not in haystack]
        if missing:
            print(f"FAIL {index}: {query}")
            print(f"  missing: {', '.join(missing)}")
        else:
            print(f"PASS {index}: {query}")
            passed += 1
    print(f"Memory eval: {passed}/{len(cases)} passed")
    return passed, len(cases)


def default_store_path() -> Path:
    configured = os.environ.get("AGENTICSE_STORE")
    if configured:
        return Path(configured)
    return Path.cwd() / ".agenticse" / "state.json"


def load_or_new(path: Path, restore_backup: bool = False) -> AgentMemorySubsystem:
    if not path.exists():
        return AgentMemorySubsystem()
    try:
        return AgentMemorySubsystem.from_snapshot(load_snapshot(path))
    except (ValueError, json.JSONDecodeError):
        backup = backup_path(path)
        if restore_backup and backup.exists():
            return AgentMemorySubsystem.from_snapshot(load_snapshot(backup))
        raise


def persist(ams: AgentMemorySubsystem, path: Path) -> None:
    save_snapshot(ams.snapshot(), path)


def build_lesson(
    content: str,
    tags: Optional[Iterable[str]] = None,
    related_classes: Optional[Iterable[str]] = None,
    severity: str = "info",
) -> Lesson:
    return Lesson(
        content=content,
        tags=list(tags or []),
        related_classes=list(related_classes or []),
        severity=severity,
    )


def read_payload(args: argparse.Namespace) -> str:
    if args.payload_file:
        path = Path(args.payload_file)
        size = path.stat().st_size
        if size > args.max_payload_bytes:
            raise ValueError(
                f"payload file is {size} bytes; limit is {args.max_payload_bytes} bytes"
            )
        return path.read_text(encoding="utf-8")
    payload = args.payload
    size = len(payload.encode("utf-8"))
    if size > args.max_payload_bytes:
        raise ValueError(
            f"payload is {size} bytes; limit is {args.max_payload_bytes} bytes"
        )
    return payload


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store",
        default=str(default_store_path()),
        help="Snapshot path. Defaults to $AGENTICSE_STORE or .agenticse/state.json.",
    )
    parser.add_argument(
        "--lock-timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for the snapshot lock before failing.",
    )
    parser.add_argument(
        "--restore-backup",
        action="store_true",
        help="Load the .bak snapshot if the primary snapshot is corrupted.",
    )


def configure_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agenticse",
        description="Persistent Agent Memory Subsystem CLI for coding agents.",
    )
    add_common_options(parser)
    subcommands = parser.add_subparsers(dest="command", required=True)

    start = subcommands.add_parser("start-task", help="Open a working-memory session.")
    start.add_argument("task")
    start.add_argument("--active-file", action="append", default=[])
    start.add_argument("--token-budget", type=int)

    awaken = subcommands.add_parser("awaken", help="Recall lessons and topology.")
    awaken.add_argument("task", nargs="?")
    awaken.add_argument("--anchor", action="append", default=[])
    awaken.add_argument("--top-k-lessons", type=int, default=5)
    awaken.add_argument("--upstream-depth", type=int, default=2)
    awaken.add_argument("--downstream-depth", type=int, default=1)

    eval_parser = subcommands.add_parser("eval", help="Run golden-query memory checks.")
    eval_parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Case format: 'query|expected term,another term|optional anchor,anchor2'.",
    )
    eval_parser.add_argument("--top-k-lessons", type=int, default=5)
    eval_parser.add_argument("--upstream-depth", type=int, default=2)
    eval_parser.add_argument("--downstream-depth", type=int, default=1)

    ingest = subcommands.add_parser("ingest", help="Ingest a sensory event.")
    ingest.add_argument("--source", required=True)
    ingest.add_argument("--kind", default="raw")
    ingest.add_argument("--max-payload-bytes", type=int, default=DEFAULT_MAX_PAYLOAD_BYTES)
    payload_group = ingest.add_mutually_exclusive_group(required=True)
    payload_group.add_argument("--payload")
    payload_group.add_argument("--payload-file")

    remember = subcommands.add_parser("remember", help="Add text to working memory.")
    remember.add_argument("text")
    remember.add_argument(
        "--resolution",
        choices=[item.value for item in Resolution],
        default=Resolution.HIGH.value,
    )

    lesson = subcommands.add_parser("record-lesson", help="Persist a reusable lesson.")
    lesson.add_argument("content")
    lesson.add_argument("--tag", action="append", default=[])
    lesson.add_argument("--class", dest="related_class", action="append", default=[])
    lesson.add_argument("--severity", default="info")

    dependency = subcommands.add_parser("record-dependency", help="Record class dependency.")
    dependency.add_argument("source_class")
    dependency.add_argument("target_class")

    call = subcommands.add_parser("record-call", help="Record method call edge.")
    call.add_argument("caller")
    call.add_argument("callee")

    finish = subcommands.add_parser("finish-task", help="Consolidate and close task.")
    finish.add_argument("--lesson", action="append", default=[])
    finish.add_argument("--tag", action="append", default=[])
    finish.add_argument("--class", dest="related_class", action="append", default=[])
    finish.add_argument("--severity", default="info")

    subcommands.add_parser("context", help="Render current working-memory context.")
    subcommands.add_parser("stats", help="Print memory store counts.")
    return parser


def run(args: argparse.Namespace) -> int:
    store_path = Path(args.store)
    with snapshot_lock(store_path, timeout_seconds=args.lock_timeout):
        return run_locked(args, store_path)


def run_locked(args: argparse.Namespace, store_path: Path) -> int:
    ams = load_or_new(store_path, restore_backup=args.restore_backup)

    if args.command == "start-task":
        ams.start_task(args.task, active_files=args.active_file, token_budget=args.token_budget)
        persist(ams, store_path)
        print(f"Started task: {args.task}")
        return 0

    if args.command == "awaken":
        prompt = args.task or getattr(ams, "_last_task_input", "")
        context = ams.awaken(
            task_input=prompt,
            explicit_anchors=args.anchor,
            top_k_lessons=args.top_k_lessons,
            upstream_depth=args.upstream_depth,
            downstream_depth=args.downstream_depth,
        ).render_prompt()
        print(context or "No relevant memory recalled.")
        return 0

    if args.command == "eval":
        passed, total = evaluate_cases(
            ams,
            args.case,
            top_k_lessons=args.top_k_lessons,
            upstream_depth=args.upstream_depth,
            downstream_depth=args.downstream_depth,
        )
        return 0 if passed == total else 1

    if args.command == "ingest":
        event = SensoryEvent(source=args.source, payload=read_payload(args), kind=args.kind)
        kept = ams.ingest([event])
        persist(ams, store_path)
        print(f"Ingested {kept} event(s).")
        return 0

    if args.command == "remember":
        ams.remember(args.text, resolution=Resolution(args.resolution))
        persist(ams, store_path)
        print("Remembered text in working memory.")
        return 0

    if args.command == "record-lesson":
        lesson = build_lesson(args.content, args.tag, args.related_class, args.severity)
        lesson_id = ams.record_lesson(lesson)
        persist(ams, store_path)
        print(f"Recorded lesson: {lesson_id}")
        return 0

    if args.command == "record-dependency":
        ams.record_dependency(args.source_class, args.target_class)
        persist(ams, store_path)
        print(f"Recorded dependency: {args.source_class} -> {args.target_class}")
        return 0

    if args.command == "record-call":
        ams.record_call(args.caller, args.callee)
        persist(ams, store_path)
        print(f"Recorded call: {args.caller} -> {args.callee}")
        return 0

    if args.command == "finish-task":
        lessons: List[Lesson] = [
            build_lesson(content, args.tag, args.related_class, args.severity)
            for content in args.lesson
        ]
        stored = ams.finish_task(lessons)
        persist(ams, store_path)
        print(f"Finished task. Stored {len(stored)} lesson(s).")
        return 0

    if args.command == "context":
        controller = getattr(ams, "_controller", None)
        print(controller.render_context() if controller is not None else "No active task.")
        return 0

    if args.command == "stats":
        snapshot_size = store_path.stat().st_size if store_path.exists() else 0
        backup = backup_path(store_path)
        print(f"Vector records: {len(ams.ltm.vector)}")
        print(f"Graph nodes: {ams.ltm.graph.node_count()}")
        print(f"Graph edges: {ams.ltm.graph.edge_count()}")
        print(f"Active task: {'yes' if getattr(ams, '_controller', None) else 'no'}")
        print(f"Store path: {store_path}")
        print(f"Snapshot size: {snapshot_size} bytes")
        print(f"Backup available: {'yes' if backup.exists() else 'no'}")
        return 0

    raise ValueError(f"Unknown command: {args.command}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = configure_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as exc:  # pragma: no cover - argparse integration path
        print(f"agenticse: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())