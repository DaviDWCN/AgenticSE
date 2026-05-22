"""End-to-end AMS demo.

Run with::

    python examples/ams_demo.py
"""

from agenticse.memory import AgentMemorySubsystem
from agenticse.memory.schemas import Lesson, SensoryEvent


def main() -> None:
    ams = AgentMemorySubsystem(token_budget=8_000)

    # --- Seed prior LTM knowledge -------------------------------------- #
    ams.record_lesson(
        Lesson(
            content="When CheckoutService throws NPE, the bug is usually in "
            "CartService.compute() ignoring an empty line-item list.",
            related_classes=["CheckoutService", "CartService"],
            tags=["debug", "checkout"],
            severity="critical",
        )
    )
    ams.record_dependency("CheckoutController", "CheckoutService")
    ams.record_dependency("CheckoutService", "CartService")
    ams.record_call("CheckoutService.pay", "CartService.compute")

    # --- New task -------------------------------------------------------- #
    task = "Fix NullPointerException in CheckoutService.pay() when cart is empty"
    ams.start_task(task, active_files=["app/CheckoutService.java"])

    print("=== Awakening context (injected into System Prompt) ===")
    print(ams.awaken_prompt())
    print()

    # --- Sensory stream -------------------------------------------------- #
    events = [
        SensoryEvent(
            source="terminal",
            payload="java.lang.NullPointerException at CheckoutService.pay(CheckoutService.java:88)",
            kind="stack_trace",
        ),
        SensoryEvent(source="metrics", payload="cpu=0.42"),  # filtered out
        SensoryEvent(source="ide", payload="patch v1 applied", kind="ast_change"),
    ]
    kept = ams.ingest(events)
    print(f"Sensory events surviving the perception filter: {kept}")
    print()

    print("=== Working memory (multi-resolution tiers) ===")
    print(ams.controller.render_context())
    print()

    # --- Reflection ------------------------------------------------------ #
    stored = ams.finish_task(
        [
            Lesson(
                content="Always guard CheckoutService.pay() with an empty-cart "
                "precondition before delegating to CartService.compute().",
                related_classes=["CheckoutService"],
                tags=["bug-fix", "checkout"],
                severity="critical",
            )
        ]
    )
    print(f"Lessons consolidated to LTM: {stored}")


if __name__ == "__main__":
    main()
