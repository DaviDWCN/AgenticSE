from agenticse.memory.schemas import (
    MemorySegments,
    Resolution,
    SensoryEvent,
    WorkingMemoryState,
    state_from_dict,
)
from agenticse.memory.working import WorkingMemoryController


def test_state_defaults_have_unique_task_ids():
    a = WorkingMemoryState()
    b = WorkingMemoryState()
    assert a.task_id != b.task_id
    assert a.token_budget == 128_000
    assert isinstance(a.memory_segments, MemorySegments)


def test_serialise_round_trip():
    state = WorkingMemoryState(
        active_file_focus=["app/Foo.java"],
        token_budget=8_000,
        memory_segments=MemorySegments(high_res=["a"], mid_res=["b"], low_res=["c"]),
        messages=[{"role": "user", "content": "hi"}],
        metadata={"k": "v"},
    )
    restored = state_from_dict(state.to_dict())
    assert restored.to_dict() == state.to_dict()


def test_add_appends_to_correct_tier():
    c = WorkingMemoryController()
    c.add("high payload", Resolution.HIGH)
    c.add("mid payload", Resolution.MID)
    c.add("low payload", Resolution.LOW)
    assert c.segments.high_res == ["high payload"]
    assert c.segments.mid_res == ["mid payload"]
    assert c.segments.low_res == ["low payload"]


def test_budget_enforcement_demotes_then_evicts():
    state = WorkingMemoryState(token_budget=20)
    c = WorkingMemoryController(state=state, safety_margin=0.0)
    for i in range(6):
        # Each block is ~10 tokens worth.
        c.add(
            f"class C{i} {{\n    public void run{i}() {{\n        doWork{i}();\n    }}\n}}",
            Resolution.HIGH,
        )
    # Older items must have been demoted, not lost outright.
    assert c.token_usage() <= 20
    # Something must remain in lower tiers (demoted) or low_res (further demoted).
    assert (c.segments.mid_res or c.segments.low_res), "expected demoted content"
    # Some representation of the newest entry must survive in *some* tier.
    survivors = c.segments.high_res + c.segments.mid_res + c.segments.low_res
    assert any("run5" in s for s in survivors)


def test_critical_traces_pinned_in_high_res():
    c = WorkingMemoryController()
    c.ingest_event(
        SensoryEvent(source="terminal", payload="NullPointerException at line 42", kind="stack_trace")
    )
    c.ingest_event(SensoryEvent(source="ide", payload="ast diff: +1 -0", kind="ast_change"))
    assert any("stack_trace" in s for s in c.segments.high_res)
    assert any("ast_change" in s for s in c.segments.mid_res)


def test_critical_traces_stay_high_res_under_budget_pressure():
    state = WorkingMemoryState(token_budget=12)
    c = WorkingMemoryController(state=state, safety_margin=0.0)
    c.ingest_event(
        SensoryEvent(
            source="terminal",
            payload="Traceback CriticalFailureService failed at line 123",
            kind="stack_trace",
        )
    )

    for i in range(4):
        c.add(
            f"class C{i} {{ public void run{i}() {{ doWork{i}(); }} }}",
            Resolution.HIGH,
        )

    assert c.token_usage() <= c.token_budget
    assert any("stack_trace" in s for s in c.segments.high_res)
    assert not any(
        "stack_trace" in s for s in c.segments.mid_res + c.segments.low_res
    )


def test_render_context_orders_tiers():
    c = WorkingMemoryController()
    c.add("HIGH-A", Resolution.HIGH)
    c.add("MID-A", Resolution.MID)
    c.add("LOW-A", Resolution.LOW)
    rendered = c.render_context()
    assert rendered.index("HIGH-A") < rendered.index("MID-A") < rendered.index("LOW-A")


def test_retention_ratio_measures_lossless_preservation():
    c = WorkingMemoryController()
    items = [
        "Stack trace: NPE in CheckoutService.computeTotal()",
        "Failing test case 42",
        "Patch attempt v1",
    ]
    for item in items:
        c.add(item, Resolution.HIGH)
    # All three must still be present verbatim.
    assert c.retention_ratio(items) == 1.0


def test_focus_replaces_active_files():
    c = WorkingMemoryController()
    c.focus(["a.py", "b.py", ""])
    assert c.state.active_file_focus == ["a.py", "b.py"]


def test_safety_margin_validation():
    import pytest

    with pytest.raises(ValueError):
        WorkingMemoryController(safety_margin=1.0)
    with pytest.raises(ValueError):
        WorkingMemoryController(safety_margin=-0.1)
