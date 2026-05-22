# AgenticSE

**AgenticSE** is a reference implementation of the **Agent Memory Subsystem
(AMS)** for industrial-grade Coding Agents. It turns the cognitive memory
model (sensory → working → long-term) into a small, well-tested,
dependency-free Python library.

## Highlights

| Spec § | Component | Module |
|---|---|---|
| §3.1 | Working-memory controller with multi-resolution paging (high / mid / low) | `agenticse.memory.working` |
| §3.2 | Vector store (episodic / lessons, Mem0 analogue) | `agenticse.memory.vector_store` |
| §3.2 | Code-Property-Graph store (Neo4j analogue, Class / Method / Field / Lesson) | `agenticse.memory.graph_store` |
| §3.2 | Long-term memory matrix (vector + graph dual engine) | `agenticse.memory.long_term` |
| §4.0 | Perception filter | `agenticse.memory.workflows.perception_filter` |
| §4.1 | Dynamic awakening (semantic recall + bounded-depth topology walk) | `agenticse.memory.workflows.awaken_for_task` |
| §4.2 | Asynchronous consolidation / reflection | `agenticse.memory.workflows.consolidate_session` |
| —   | One-stop façade for orchestrators | `agenticse.memory.AgentMemorySubsystem` |

## Install

```bash
pip install -e .
pip install -e ".[dev]"   # for pytest
```

## Tests

```bash
python -m pytest tests/ -v
```

51 unit tests cover every layer, workflow, persistence snapshots and the CLI.

## Agent CLI

AgenticSE includes a small stdlib-only CLI for coding agents. It persists a
workspace snapshot at `.agenticse/state.json` by default, so repeated shell
invocations share long-term lessons, topology and the active working-memory
session. Writes are atomic, keep a `.bak` backup and run under a local snapshot
lock.

```bash
agenticse start-task "Fix checkout total regression" --active-file app/CheckoutService.java
agenticse record-lesson "Null-check cart before computing tax" --class CartService --tag bug-fix
agenticse record-dependency CheckoutService CartService
agenticse awaken "Fix CheckoutService cart bug" --anchor CheckoutService
agenticse ingest --source terminal --kind stack_trace --payload-file /tmp/error.txt
agenticse stats
agenticse finish-task --lesson "Checkout totals need empty-cart fixture coverage"
```

Use `--store path/to/state.json` or `AGENTICSE_STORE` to isolate memory per
workspace, branch, benchmark run or agent. Use `--restore-backup` if the primary
snapshot file is corrupted.

## Quick start

```python
from agenticse.memory import AgentMemorySubsystem
from agenticse.memory.schemas import Lesson, SensoryEvent

ams = AgentMemorySubsystem(token_budget=8_000)

# Seed prior LTM knowledge.
ams.record_lesson(Lesson(
    content="When CheckoutService throws NPE, inspect CartService.compute() first.",
    related_classes=["CheckoutService", "CartService"],
    tags=["debug"],
))
ams.record_dependency("CheckoutService", "CartService")

# Begin a new task — the awakening prompt is ready to be spliced into the System Prompt.
ams.start_task("Fix NPE in CheckoutService when cart is empty",
               active_files=["app/CheckoutService.java"])
print(ams.awaken_prompt())

# Stream IDE / terminal events; only the relevant ones reach working memory.
ams.ingest([
    SensoryEvent(source="terminal", payload="NPE at line 88", kind="stack_trace"),
    SensoryEvent(source="metrics",  payload="cpu=0.42"),       # filtered out
])

# Reflect: persist new lessons + the abstract trajectory into the LTM.
ams.finish_task([
    Lesson(content="Guard CheckoutService.pay() with an empty-cart precondition.",
           related_classes=["CheckoutService"], tags=["bug-fix"]),
])
```

See [`examples/ams_demo.py`](examples/ams_demo.py) for the full lifecycle.

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    IDE / Terminal / User Input                    │
└────────────────────────────────┬───────────────────────────────────┘
                                 │  SensoryEvent stream
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  perception_filter   →   WorkingMemoryController (LangGraph State) │
│                                                                    │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐           │
│   │  HIGH-RES    │←──│   MID-RES    │←──│   LOW-RES    │ (paging)  │
│   │ raw code +   │   │ AST sigs +   │   │ abstract     │           │
│   │ stack traces │   │ deps         │   │ trajectory   │           │
│   └──────────────┘   └──────────────┘   └──────────────┘           │
└────────────────▲───────────────────────────────────┬───────────────┘
                 │ (1) awaken                        │ (2) consolidate
                 │                                   ▼
┌────────────────┴───────────────────────────────────────────────────┐
│                  LongTermMemoryMatrix (dual engine)                │
│   ┌──────────────────────────┐  ┌────────────────────────────┐     │
│   │ InMemoryVectorStore      │  │ InMemoryGraphStore (CPG)   │     │
│   │ — Mem0-style lessons     │  │ — Class/Method/Field/Lesson│     │
│   │ — content-hash dedup     │  │ — CALLS / DEPENDS_ON /     │     │
│   │ — hybrid sem+lex search  │  │   LESSON_FOR_CLASS         │     │
│   └──────────────────────────┘  └────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────┘
```

### Design decisions

* **Dependency-free core.** Embeddings are deterministic feature-hashed
  vectors; token counts use a CJK-aware heuristic. Production deployments
  swap in `tiktoken` + a real embedding model + a real graph DB by
  re-implementing the four-method interfaces.
* **No raw history to the LLM.** `WorkingMemoryController._enforce_budget`
  guarantees the rendered context never exceeds the configured budget;
  older entries are *demoted* (high → mid → low) before being evicted.
* **Stack traces are pinned** to the high-res tier so the §1.1 retention
  target (≥ 95 % lossless retention of critical traces) is structurally
  enforced.
* **Dual-engine recall.** Awakening fans out a vector lesson search *and*
  a bounded-depth graph walk (2 upstream / 1 downstream by default) so the
  agent sees both "what bit us last time" and "what is connected to this
  symbol".

## Layout

```
agenticse/
  memory/
    __init__.py          # public surface
    ams.py               # AgentMemorySubsystem facade
    embeddings.py        # token estimator + hash embeddings
    graph_store.py       # InMemoryGraphStore (CPG)
    long_term.py         # LongTermMemoryMatrix
    schemas.py           # dataclasses (State, Segments, Lesson, ...)
    vector_store.py      # InMemoryVectorStore
    working.py           # WorkingMemoryController (multi-res paging)
    workflows.py         # perception / awakening / consolidation
examples/
  ams_demo.py
tests/
  test_ams.py
  test_graph_store.py
  test_vector_store.py
  test_workflows.py
  test_working_memory.py
```
