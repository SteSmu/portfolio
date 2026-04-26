"""Smoke tests — package importable, CLI registered, version exposed."""

from __future__ import annotations

from typer.testing import CliRunner


def test_package_importable():
    import pt

    assert pt.__version__


def test_cli_version():
    from pt.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "pt" in result.stdout


def test_cli_help():
    from pt.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Portfolio Tracker" in result.stdout


def test_api_app_importable():
    from pt.api.app import app as fastapi_app

    assert fastapi_app.title == "Portfolio Tracker API"
