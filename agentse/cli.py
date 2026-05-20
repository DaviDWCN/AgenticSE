"""
CLI entry point for AgenticSE.

Usage
-----
    agentse run --title "User authentication" --description "..."
    agentse status
    agentse trends
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.json import JSON
    from rich.panel import Panel
    from rich.table import Table

    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

if _HAS_RICH:
    app = typer.Typer(
        name="agentse",
        help="Autonomous Multi-Agent Software Engineering Team CLI",
        add_completion=False,
    )
    console = Console()

    @app.command()
    def run(
        title: str = typer.Option(..., "--title", "-t", help="Feature title"),
        description: str = typer.Option(
            ..., "--description", "-d", help="Feature description / requirement"
        ),
        sprint: Optional[str] = typer.Option(
            None, "--sprint", "-s", help="Sprint name"
        ),
        store: Optional[Path] = typer.Option(
            None, "--store", help="Path to memory store file"
        ),
        concurrency: int = typer.Option(4, "--concurrency", "-c"),
        output_json: bool = typer.Option(
            False, "--json", help="Output raw JSON result"
        ),
    ) -> None:
        """Run an end-to-end feature development sprint."""
        from agentse.team import AgentTeam

        team = AgentTeam(store_path=store, concurrency=concurrency)
        summary = asyncio.run(
            team.run_feature(title=title, description=description, sprint_name=sprint)
        )

        if output_json:
            console.print_json(json.dumps(summary, indent=2, default=str))
            return

        console.print(
            Panel.fit(
                f"[bold green]Sprint completed![/]\n"
                f"Tasks: {summary['completed']}/{summary['total']} completed, "
                f"{summary['failed']} failed\n"
                f"Avg duration: {summary['avg_task_duration_s']:.3f}s",
                title=f"[bold]{title}[/]",
            )
        )

    @app.command()
    def status(
        store: Optional[Path] = typer.Option(None, "--store"),
    ) -> None:
        """Display current agent team status."""
        from agentse.team import AgentTeam

        team = AgentTeam(store_path=store)
        data = team.team_status()

        table = Table(title="Agent Team Status")
        table.add_column("Role", style="cyan")
        table.add_column("Status")
        table.add_column("Completed")
        table.add_column("Failed")
        table.add_column("Avg Duration (s)")
        table.add_column("Success Rate")

        for role, info in data.items():
            m = info["metrics"]
            table.add_row(
                role,
                info["status"],
                str(m["tasks_completed"]),
                str(m["tasks_failed"]),
                str(m["avg_duration_s"]),
                f"{m['success_rate']:.0%}",
            )

        console.print(table)

    @app.command()
    def trends(
        store: Optional[Path] = typer.Option(None, "--store"),
    ) -> None:
        """Show learning trend report across all sprints."""
        from agentse.team import AgentTeam

        team = AgentTeam(store_path=store)
        report = team.trend_report()
        console.print(Panel(JSON(json.dumps(report, indent=2)), title="Trend Report"))

else:
    # Fallback when typer/rich are not installed
    app = None  # type: ignore[assignment]
