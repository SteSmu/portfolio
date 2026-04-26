# Portfolio Tracker

Multi-Asset Portfolio-Tracking & Analyse — read-only, korrekte Zahlen, weltklasse UX.

**Status:** Phase 0 — Bootstrap.

## Vision

> Ich oeffne die App, sehe in 3 Sekunden meinen Portfolio-Stand, was sich seit gestern/letzter Woche/seit Kauf getan hat, sehe pro Asset die wichtigsten News + AI-Insights, und kann zu 100% den Zahlen vertrauen — egal ob Stocks, Crypto, ETFs, FX oder Rohstoffe.

## Stack

- **Backend:** Python 3.12 + FastAPI + Typer + psycopg 3
- **DB:** TimescaleDB (shared mit `claude-trader`)
- **Frontend:** React 19 + TypeScript + Vite + Tailwind (Phase 5)
- **Money-Math:** `decimal.Decimal` — niemals `float` fuer Geldbetraege

## Quick Start

```bash
# 1) Shared TimescaleDB starten (aus claude-trader)
cd ../claude-trader && docker compose up -d timescaledb

# 2) Portfolio-Repo Setup
cd ../portfolio
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3) DB-Migration (Phase 1)
# pt db migrate

# 4) Smoke-Tests
pytest

# 5) CLI
pt --version
pt --help
```

## Repo-Struktur

```
pt/                  # Python-Package
  cli.py             # Typer entry: `pt`
  api/               # FastAPI app + routes
  db/                # Schema + connection
  data/              # Multi-asset fetcher (CoinGecko, Twelve Data, Frankfurter, ...)
  importers/         # PDF/CSV parser pro Broker
  performance/       # TWR, MWR, Cost-Basis, Metriken
  insights/          # LLM-basierte Insights
  audit/             # Reconciliation, Corporate Actions
  tax/               # Realized/Unrealized, DE-Reports
  trader_bridge/     # claude-trader Integration
frontend/            # React + Vite (Phase 5)
tests/               # pytest
```

## Implementierungs-Phasen

Siehe [.claude/plans/portfolio-bootstrap.md](.claude/plans/portfolio-bootstrap.md) fuer den vollen Plan.

| Phase | Inhalt | Status |
|-------|--------|--------|
| 0 | Bootstrap, Skeleton, Smoke-Test | ✓ |
| 1 | DB-Schema + Multi-Asset Fetcher | — |
| 2 | Performance-Engine + Reference-Tests | — |
| 3 | PDF-Importer | — |
| 4 | API + CLI | — |
| 5 | Frontend MVP | — |
| 6 | News + LLM-Insights | — |
| 7 | Tax + Reconciliation | — |
| 8 | Polish, Mobile-Responsive | — |
| 9 | claude-trader Bridge | — |

## Kein Trading

Dieses Tool fuehrt **keine Orders aus** und schreibt **niemals** auf Broker-APIs.
Eingaben erfolgen ueber PDF-Import, CSV-Import oder manuelle Eingabe.

## Lizenz

Privat / unveroeffentlicht.
