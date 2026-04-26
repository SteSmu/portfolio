"""CLI sync subcommand smoke tests."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner


def test_sync_subcommand_registered():
    from pt.cli import app

    result = CliRunner().invoke(app, ["sync", "--help"])
    assert result.exit_code == 0
    for cmd in ["fx", "crypto", "stock"]:
        assert cmd in result.stdout


@pytest.mark.parametrize("sub", ["fx", "crypto", "stock"])
def test_each_sync_command_help_works(sub):
    from pt.cli import app

    result = CliRunner().invoke(app, ["sync", sub, "--help"])
    assert result.exit_code == 0
