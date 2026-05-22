---
name: agenticse-memory
description: "Use when: managing coding-agent task memory with AgenticSE, recalling prior debugging lessons, recording code topology, ingesting terminal or IDE events, or consolidating reusable engineering lessons."
argument-hint: "task or memory operation"
---

# AgenticSE Memory

Use this skill when a coding task benefits from durable memory across tool calls or sessions. AgenticSE provides a local JSON-backed memory snapshot through the `agenticse` CLI.

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

## Guidance

- Store concise lessons, not raw transcripts.
- Ingest terminal failures, stack traces, active-file changes and important user decisions.
- Do not ingest secrets, credentials or noisy telemetry.
- Prefer explicit anchors for recall when the task names a class, method, module or file.