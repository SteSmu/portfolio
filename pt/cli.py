"""Portfolio Tracker CLI — `pt`.

Entry point. Subcommands are registered via Typer sub-apps in cli_*.py modules.
Mirrors the layout used by claude-trader's `ct` CLI for consistency.
"""

from __future__ import annotations

import typer
from rich.console import Console

from pt import __version__

app = typer.Typer(
    name="pt",
    help="Portfolio Tracker — multi-asset, read-only analysis & overview.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(f"pt {__version__}")
        raise typer.Exit()


# Sub-apps registered here as phases land.
from pt import cli_asset, cli_db, cli_holdings, cli_portfolio, cli_sync, cli_tx

app.add_typer(cli_db.app, name="db")
app.add_typer(cli_portfolio.app, name="portfolio")
app.add_typer(cli_tx.app, name="tx")
app.add_typer(cli_holdings.app, name="holdings")
app.add_typer(cli_asset.app, name="asset")
app.add_typer(cli_sync.app, name="sync")


if __name__ == "__main__":
    app()
