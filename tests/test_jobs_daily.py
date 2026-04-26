"""Daily orchestrator — pin the structure of the result + isolation between steps."""

from __future__ import annotations

from unittest.mock import patch

from pt.jobs import daily as _daily


def _ok():
    return {"ok": True, "rows_written": 1}


def test_run_returns_ok_when_all_steps_pass():
    """Happy path — every step returns ok, overall ok=True."""
    with patch.object(_daily, "_list_active_portfolio_ids", return_value=[1, 2]), \
         patch.object(_daily, "_step_fx", return_value=_ok()), \
         patch.object(_daily, "_step_auto_prices", return_value={**_ok(), "portfolios": 2}), \
         patch.object(_daily, "_step_benchmarks", return_value={**_ok(), "benchmarks": 4}), \
         patch.object(_daily, "_step_snapshots", return_value={**_ok(), "portfolios": 2}):
        result = _daily.run()
    assert result["ok"] is True
    assert result["portfolios"] == 2
    assert set(result["steps"].keys()) == {"fx", "auto_prices", "benchmarks", "snapshots"}


def test_run_fails_overall_when_any_step_fails():
    """One step returning ok=False propagates to the overall flag — but the
    other steps still execute (cron must report partial successes)."""
    with patch.object(_daily, "_list_active_portfolio_ids", return_value=[1]), \
         patch.object(_daily, "_step_fx", return_value=_ok()), \
         patch.object(_daily, "_step_auto_prices", return_value={"ok": False, "error": "td down"}), \
         patch.object(_daily, "_step_benchmarks", return_value=_ok()), \
         patch.object(_daily, "_step_snapshots", return_value=_ok()):
        result = _daily.run()
    assert result["ok"] is False
    assert result["steps"]["auto_prices"]["error"] == "td down"
    # Snapshots still ran despite auto_prices failing.
    assert result["steps"]["snapshots"]["ok"] is True


def test_run_skips_per_portfolio_steps_when_no_active_portfolios():
    """Cron firing on a fresh DB shouldn't blow up; FX + benchmarks still
    execute because they're portfolio-independent."""
    with patch.object(_daily, "_list_active_portfolio_ids", return_value=[]), \
         patch.object(_daily, "_step_fx", return_value=_ok()) as fx, \
         patch.object(_daily, "_step_benchmarks", return_value=_ok()) as bm, \
         patch.object(_daily, "_step_auto_prices") as ap, \
         patch.object(_daily, "_step_snapshots") as sn:
        result = _daily.run()
    assert result["ok"] is True
    assert result["portfolios"] == 0
    assert "skipped" in result["steps"]["auto_prices"]
    assert "skipped" in result["steps"]["snapshots"]
    fx.assert_called_once()
    bm.assert_called_once()
    ap.assert_not_called()
    sn.assert_not_called()
