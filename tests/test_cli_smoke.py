"""CLI smoke tests for new sub-apps. Verifies registration + --help on every command."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from tests.conftest import requires_db


def _runner() -> CliRunner:
    return CliRunner()


def test_root_help_lists_all_sub_apps():
    from pt.cli import app

    result = _runner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in ["db", "portfolio", "tx", "holdings", "asset"]:
        assert sub in result.stdout


@pytest.mark.parametrize("sub", ["db", "portfolio", "tx", "holdings", "asset"])
def test_each_sub_app_help_works(sub):
    from pt.cli import app

    result = _runner().invoke(app, [sub, "--help"])
    assert result.exit_code == 0


@requires_db
def test_portfolio_create_then_list_via_cli_json():
    from pt.cli import app
    from pt.db import portfolios as _portfolios

    runner = _runner()
    name = "_pt_cli_smoke_test"

    # Cleanup any leftovers from prior failed runs
    existing = _portfolios.get_by_name(name)
    if existing:
        _portfolios.delete_hard(existing["id"])

    create = runner.invoke(app, ["portfolio", "create", name, "--json"])
    assert create.exit_code == 0, create.stdout
    payload = json.loads(create.stdout)
    pid = payload["id"]

    try:
        listing = runner.invoke(app, ["portfolio", "list", "--json"])
        assert listing.exit_code == 0
        rows = json.loads(listing.stdout)
        assert any(r["id"] == pid for r in rows)
    finally:
        _portfolios.delete_hard(pid)


@requires_db
def test_portfolio_create_duplicate_returns_conflict_exit_5():
    from pt.cli import app
    from pt.db import portfolios as _portfolios

    name = "_pt_cli_dup_test"
    existing = _portfolios.get_by_name(name)
    if existing:
        _portfolios.delete_hard(existing["id"])

    runner = _runner()
    first = runner.invoke(app, ["portfolio", "create", name, "--json"])
    pid = json.loads(first.stdout)["id"]
    try:
        second = runner.invoke(app, ["portfolio", "create", name, "--json"])
        assert second.exit_code == 5  # conflict per CLI conventions
    finally:
        _portfolios.delete_hard(pid)


@requires_db
def test_portfolio_show_unknown_returns_exit_3():
    from pt.cli import app

    result = _runner().invoke(app, ["portfolio", "show", "99999999", "--json"])
    assert result.exit_code == 3
