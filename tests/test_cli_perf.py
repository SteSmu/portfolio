"""CLI smoke tests for `pt perf`."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from tests.conftest import requires_db


def test_perf_subcommand_registered():
    from pt.cli import app
    res = CliRunner().invoke(app, ["perf", "--help"])
    assert res.exit_code == 0
    for sub in ["cost-basis", "realized", "summary"]:
        assert sub in res.stdout


@pytest.mark.parametrize("sub", ["cost-basis", "realized", "summary"])
def test_each_perf_command_help_works(sub):
    from pt.cli import app
    res = CliRunner().invoke(app, ["perf", sub, "--help"])
    assert res.exit_code == 0


@requires_db
def test_perf_summary_end_to_end(isolated_portfolio):
    """End-to-end: add a buy + partial sell, then `pt perf summary` should report
    the right realized P&L and open cost basis."""
    from pt.cli import app
    from pt.db import transactions as _tx

    # buy 10 @ 100 fees 0
    _tx.insert(portfolio_id=isolated_portfolio, symbol="X", asset_type="stock",
                action="buy", executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                quantity=Decimal("10"), price=Decimal("100"),
                trade_currency="USD")
    # sell 4 @ 120 → realized = 4*(120-100) = 80
    _tx.insert(portfolio_id=isolated_portfolio, symbol="X", asset_type="stock",
                action="sell", executed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                quantity=Decimal("4"), price=Decimal("120"),
                trade_currency="USD")

    res = CliRunner().invoke(app, ["perf", "summary",
                                    "-p", str(isolated_portfolio), "--json"])
    assert res.exit_code == 0, res.stdout
    payload = json.loads(res.stdout)
    assert payload["open_lot_count"] == 1
    assert Decimal(payload["open_cost_basis"]) == Decimal("600")  # 6 left @ 100
    assert Decimal(payload["realized_pnl"]) == Decimal("80")


@requires_db
def test_perf_realized_filters_by_year(isolated_portfolio):
    from pt.cli import app
    from pt.db import transactions as _tx

    # 2025 sell — realized 50
    _tx.insert(portfolio_id=isolated_portfolio, symbol="A", asset_type="stock",
                action="buy",  executed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                quantity=Decimal("5"), price=Decimal("100"), trade_currency="USD")
    _tx.insert(portfolio_id=isolated_portfolio, symbol="A", asset_type="stock",
                action="sell", executed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
                quantity=Decimal("5"), price=Decimal("110"), trade_currency="USD")
    # 2026 sell — realized 100
    _tx.insert(portfolio_id=isolated_portfolio, symbol="B", asset_type="stock",
                action="buy",  executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                quantity=Decimal("10"), price=Decimal("100"), trade_currency="USD")
    _tx.insert(portfolio_id=isolated_portfolio, symbol="B", asset_type="stock",
                action="sell", executed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                quantity=Decimal("10"), price=Decimal("110"), trade_currency="USD")

    runner = CliRunner()

    res_all = runner.invoke(app, ["perf", "realized",
                                   "-p", str(isolated_portfolio), "--json"])
    payload_all = json.loads(res_all.stdout)
    assert Decimal(payload_all["total"]) == Decimal("150")  # 50 + 100

    res_2025 = runner.invoke(app, ["perf", "realized",
                                    "-p", str(isolated_portfolio),
                                    "--year", "2025", "--json"])
    payload_2025 = json.loads(res_2025.stdout)
    assert Decimal(payload_2025["total"]) == Decimal("50")
    assert payload_2025["match_count"] == 1


@requires_db
def test_perf_cost_basis_returns_open_lots_via_json(isolated_portfolio):
    from pt.cli import app
    from pt.db import transactions as _tx

    _tx.insert(portfolio_id=isolated_portfolio, symbol="ZZ", asset_type="stock",
                action="buy", executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                quantity=Decimal("3"), price=Decimal("50"),
                trade_currency="USD")

    res = CliRunner().invoke(app, ["perf", "cost-basis",
                                    "-p", str(isolated_portfolio), "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert len(payload["open_lots"]) == 1
    assert payload["open_lots"][0]["symbol"] == "ZZ"
    assert Decimal(payload["open_lots"][0]["quantity"]) == Decimal("3")
