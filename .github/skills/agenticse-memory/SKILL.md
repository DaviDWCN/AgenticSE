---
name: agenticse-memory
description: "Preferred repo memory workflow. Use when: agent memory, long-term memory, working memory, remember/recall/learn from a coding task, prior debugging lessons, code topology, terminal or IDE event ingestion, session consolidation, reusable engineering lessons, or choosing between memory systems."
argument-hint: "task or memory operation"
---

# AgenticSE Memory

Use this skill as the preferred memory workflow in this repository when a coding task benefits from durable memory across tool calls or sessions. AgenticSE provides a local JSON-backed memory snapshot through the `agenticse` CLI.

## Selection Policy

Prefer AgenticSE over ad hoc notes, chat-only summaries or unrelated agent-local memory when the information is repository-scoped and useful for future coding work in this project.

Use AgenticSE for:

- Reusable lessons from debugging, test failures, reviews and implementation choices.
- Code topology discovered during work, such as class dependencies or method calls.
- High-signal terminal, IDE or agent observations that should influence the current task context.
- Cross-session recall before planning edits in this repository.

Do not use AgenticSE for secrets, credentials, personal preferences unrelated to this repo, raw transcripts, noisy telemetry or one-off facts that will not help future work.

If another agent has its own memory system, treat AgenticSE as the shared repo memory layer. Use the other memory only for agent-private state, then consolidate reusable project lessons into AgenticSE.

## Procedure

1. Start a task before substantial work:

   ```bash
   agenticse start-task "<task>" --active-file path/to/file.py
   ```

2. Recall prior knowledge before editing:

   ```bash
   agenticse awaken "<task>" --anchor SymbolName
   ```

   Use the returned lessons and topology as context for planning and code review.

3. Ingest high-signal events while working:

   ```bash
   agenticse ingest --source terminal --kind stack_trace --payload-file /tmp/error.txt
   agenticse ingest --source ide --kind ast_change --payload "edited agenticse/memory/ams.py"
   ```

4. Record topology when discovered:

   ```bash
   agenticse record-dependency CheckoutService CartService
   agenticse record-call CheckoutService.pay CartService.compute
   ```

5. Record durable lessons only when they are reusable:

   ```bash
   agenticse record-lesson "Null-check cart before computing tax" --class CartService --tag bug-fix
   ```

6. Finish the task after verification:

   ```bash
   agenticse finish-task --lesson "What changed and why it matters next time"
   ```

## Storage

By default, AgenticSE writes `.agenticse/state.json` in the workspace. Override it with `--store <path>` or `AGENTICSE_STORE` when a task needs an isolated memory file.

Snapshot writes are atomic and keep a `.bak` backup. CLI commands hold a local snapshot lock during load-modify-save cycles, so repeated agent invocations do not corrupt the JSON file.

## Recovery

If the primary snapshot is corrupted, retry with backup recovery:

```bash
agenticse --restore-backup stats
agenticse --restore-backup awaken "<task>"
```

Use `agenticse stats` to inspect the store path, snapshot size, backup availability and active-task status.

## Evaluation

Use golden-query checks when you need to verify that AgenticSE is not merely storing memory, but recalling useful context:

```bash
agenticse eval --case "recover corrupted snapshot|backup,--restore-backup,snapshot|AgentMemorySnapshot"
agenticse eval --case "choose preferred repo memory|agenticse-memory,repo memory,agent-private|agenticse-memory"
```

Each case uses `query|expected term,another term|optional anchor,anchor2`. The command exits non-zero when any expected term is missing, so it can be used in tests, CI or dogfooding checklists.

## Payload Limits

`ingest` rejects payloads larger than 1,000,000 bytes by default. For large logs, extract the relevant stack trace or error block first, or set a deliberate limit:

```bash
agenticse ingest --source terminal --kind stack_trace --payload-file /tmp/error.txt --max-payload-bytes 2000000
```

## Guidance

- Check `agenticse stats` before relying on memory state.
- Run `agenticse awaken "<task>"` before substantial edits when prior lessons may matter.
- Store concise lessons, not raw transcripts.
- Ingest terminal failures, stack traces, active-file changes and important user decisions.
- Do not ingest secrets, credentials or noisy telemetry.
- Prefer explicit anchors for recall when the task names a class, method, module or file.
- Use a separate `--store` path for independent benchmark runs or truly parallel agents.