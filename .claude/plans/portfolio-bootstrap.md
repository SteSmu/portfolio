# Portfolio — Persoenliches Multi-Asset Tracking-Tool (Read-only Analyse & Overview)

## Context

Wir bauen unter `/Users/stefan/projects/private/prod/portfolio/` (Repo aktuell leer, nur `.git`) ein persoenliches Portfolio-Tracking-Tool. Es ist **kein Trading-Tool** — keine Order-Ausfuehrung, keine Broker-Schreibzugriffe. Ziel: Stefan und spaeter ggf. weitere Nutzer bekommen in kuerzester Zeit einen weltklasse Ueberblick ueber ihr Portfolio, die Entwicklung einzelner Assets, News + Insights pro Asset, sowie korrekte Performance-Zahlen (TWR/MWR/XIRR) ueber beliebige Zeitraeume.

**Warum jetzt:** Marktstudie zeigt eine klare Luecke — bestehende Tools (Sharesight, Parqet, Ghostfolio, Empower, Kubera) glaenzen jeweils in einem Bereich, aber **kein** Tool kombiniert (a) wirklich Multi-Asset (Crypto + Stocks + ETFs + FX + Rohstoffe in einem) mit (b) zahlenkorrekter Performance-Berechnung mit (c) erstklassiger UX und (d) tiefen LLM-basierten Insights pro Asset. Gleichzeitig haben wir mit `claude-trader` (`/Users/stefan/projects/private/prod/claude-trader/`) bereits eine produktive Datenpipeline, TimescaleDB-Infrastruktur, Indikatoren-Library, FastAPI-Stack und ein React-19-Frontend — Wiederverwendung ist ~70% moeglich. Mittelfristig soll claude-trader read-only auf das Portfolio zugreifen, um asset-spezifische Trading-Tipps geben zu koennen (heute nur BTC).

**Outcome:** Ein lokal laufendes (single-user, spaeter multi-user-ready), self-hosted Tool mit CLI + Web-UI, das gekaufte Assets per PDF-Broker-Statement-Import erfasst, ihre Entwicklung tagesgenau trackt, Performance auf Profi-Niveau berechnet, News+Insights pro Asset liefert und korrekte Zahlen zu 100% garantiert (Decimal-Math, Audit-Trail, Reconciliation gegen Broker-Statements, Corporate-Actions-Auto-Handling).

**Bestaetigte Scope-Entscheidungen** (User-Antworten via AskUserQuestion):
1. **Multi-Asset komplett** — Crypto + Aktien + ETFs + FX + Rohstoffe von Anfang an
2. **Shared TimescaleDB** mit `claude-trader` — generalisiertes Schema, gemeinsame Preisdaten
3. **Reines Analyse/Overview-Tool** — kein Trading, keine Broker-API-Schreibzugriffe; **PDF-Import** von Broker-Uebersichten als primaerer Eingabeweg (User liefert Beispiel-PDF separat)
4. **Single-User** mit `user_id`-Column vorbereitet (NULLable), spaeter Multi-User-Auth nachruestbar

---

## Vision in einem Satz

> "Ich oeffne die App, sehe in 3 Sekunden meinen Portfolio-Stand, was sich seit gestern/letzter Woche/seit Kauf getan hat, sehe pro Asset die wichtigsten News + AI-Insights, und kann zu 100% den Zahlen vertrauen — egal ob Stocks, Crypto, ETFs, FX oder Rohstoffe."

---

## Architektur

### Stack-Entscheidung (analog claude-trader fuer maximale Wiederverwendung)

| Layer | Technologie | Begruendung |
|-------|-------------|-------------|
| Backend | Python 3.12, FastAPI 0.135, Typer CLI, psycopg 3 | 1:1 zu claude-trader, shared deps |
| DB | TimescaleDB 16 (PostgreSQL + Timescale) | shared mit claude-trader, ACID, Hypertables fuer Preise, JSONB fuer flexible Metadata |
| Frontend | React 19 + TypeScript 5.9 + Vite 8 + TailwindCSS 4 + TanStack Query 5 | gleiche Tooling-Chain wie claude-trader-Frontend |
| Charts | Lightweight-Charts 5 (Asset-Detail) + Recharts (Allocation/Performance) | Lightweight-Charts hat claude-trader bereits |
| Money-Math | Python `decimal.Decimal` (28 Stellen), DB `NUMERIC(20,8)` | **niemals Float** fuer Geldbetraege — kritisch fuer Korrektheit |
| Container | docker-compose, shared TimescaleDB-Service | gemeinsamer DB-Container `ct-timescaledb` |

### Repo-Struktur

```
/Users/stefan/projects/private/prod/portfolio/
├── pt/                          # Python package (analog ct/)
│   ├── cli.py                   # Typer Entry: `pt`
│   ├── cli_holdings.py
│   ├── cli_import.py
│   ├── cli_sync.py
│   ├── cli_perf.py
│   ├── api/
│   │   ├── app.py               # FastAPI app
│   │   └── routes/
│   │       ├── holdings.py
│   │       ├── performance.py
│   │       ├── transactions.py
│   │       ├── news.py
│   │       ├── insights.py
│   │       ├── allocation.py
│   │       └── tax.py
│   ├── data/                    # Multi-Asset Fetcher
│   │   ├── coingecko.py         # Crypto (Free, no key)
│   │   ├── twelve_data.py       # Stocks/ETFs (800 calls/day free)
│   │   ├── eodhd.py             # Stocks Global (paid, optional)
│   │   ├── frankfurter.py       # FX (ECB, free, no limits)
│   │   ├── marketaux.py         # News (free tier)
│   │   ├── finnhub.py           # News + Earnings (free tier)
│   │   └── corporate_actions.py # Splits, Dividends, Spinoffs
│   ├── db/
│   │   ├── schema_portfolio.sql # Portfolio-spezifische Tables
│   │   └── migrations/          # Versionierte Migrations
│   ├── importers/               # PDF/CSV-Parser
│   │   ├── pdf/
│   │   │   ├── trade_republic.py
│   │   │   ├── scalable_capital.py
│   │   │   ├── comdirect.py
│   │   │   ├── ing.py
│   │   │   └── generic.py       # Heuristik-basiert
│   │   ├── csv/
│   │   │   ├── coinbase.py
│   │   │   ├── binance.py
│   │   │   ├── kraken.py
│   │   │   └── generic.py       # Mapping-UI-Backed
│   │   └── format_detect.py     # Auto-Erkennung
│   ├── performance/             # Zahlen-korrekte Berechnungen
│   │   ├── money.py             # Decimal-Helpers, FX-Konvertierung
│   │   ├── twr.py               # Time-Weighted Return
│   │   ├── mwr.py               # Money-Weighted (XIRR via Newton-Raphson)
│   │   ├── metrics.py           # Sharpe, Sortino, MaxDD, Calmar, Vola
│   │   ├── cost_basis.py        # FIFO / LIFO / Average / SpecID
│   │   └── benchmarks.py        # S&P500, MSCI World, Custom
│   ├── tax/
│   │   ├── realize.py           # Realized vs. Unrealized
│   │   ├── holding_period.py    # Short/Long-Term (de-Spekulationsfrist)
│   │   └── reports.py           # PDF/CSV-Tax-Reports (DE-Format)
│   ├── insights/
│   │   ├── llm.py               # OpenRouter-Wrapper (reuse von claude-trader)
│   │   ├── earnings_summary.py  # AI Summary aus Transcripts
│   │   ├── sentiment.py         # cached daily
│   │   └── theme_detect.py      # correlated moves clustern
│   ├── trader_bridge/           # Read-only Brueck zu claude-trader
│   │   └── signals.py           # holt aktuelle Signals fuer Holdings
│   └── audit/
│       ├── reconciliation.py    # taegliches Compare gegen letztes PDF
│       └── corp_actions.py      # auto-apply Splits/Dividends
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Holdings.tsx
│   │   │   ├── AssetDetail.tsx
│   │   │   ├── Performance.tsx
│   │   │   ├── Allocation.tsx
│   │   │   ├── Transactions.tsx
│   │   │   ├── Income.tsx       # Dividenden-Kalender
│   │   │   ├── NewsInsights.tsx
│   │   │   ├── Tax.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/
│   │   │   ├── PortfolioValueCard.tsx
│   │   │   ├── PerformanceChart.tsx
│   │   │   ├── AllocationPie.tsx
│   │   │   ├── HoldingRow.tsx
│   │   │   ├── AssetNewsCard.tsx
│   │   │   └── ImportWizard.tsx
│   │   └── api/client.ts
│   └── package.json             # Vite + React 19 + TS + Tailwind
├── tests/
│   ├── conftest.py              # uebernimmt make_ohlcv aus claude-trader (symlink/import)
│   ├── test_twr.py              # Reference-Cases (Excel-XIRR, CFA-Beispiele)
│   ├── test_mwr.py
│   ├── test_cost_basis.py       # FIFO/LIFO Edge Cases
│   ├── test_corp_actions.py     # AAPL 4:1, TSLA 5:1, AMZN 20:1
│   ├── test_fx.py               # Multi-Currency Rounding
│   ├── test_pdf_trade_republic.py # gegen User-PDF
│   └── test_reconciliation.py
├── docker-compose.yml           # nutzt shared timescaledb-Service (extern)
├── Dockerfile
├── pyproject.toml
├── .env.example
└── .cortex.json
```

### Code-Sharing mit claude-trader

**Strategie**: Symlink-basiertes lokales Sharing in Phase 1, optional spaeter Python-Package extrahieren.

```bash
cd portfolio/
ln -s ../claude-trader/ct/db/connection.py        pt/db/_ct_connection.py
ln -s ../claude-trader/ct/data/binance.py         pt/data/_ct_binance.py
ln -s ../claude-trader/ct/indicators              pt/indicators
ln -s ../claude-trader/tests/conftest.py          tests/_ct_conftest.py
```

**Wiederverwendete Module** (ohne Aenderung):
- [ct/db/connection.py](claude-trader/ct/db/connection.py) — psycopg-Context-Manager
- [ct/data/fetcher.py](claude-trader/ct/data/fetcher.py:54) — `insert_candles_batch()` (executemany, 10-50x speed)
- [ct/data/binance.py](claude-trader/ct/data/binance.py) — async HTTP, Pagination, Semaphore
- [ct/indicators/ta.py](claude-trader/ct/indicators/ta.py) — pandas-ta Wrapper, OHLCV-agnostisch
- [tests/conftest.py](claude-trader/tests/conftest.py) — `make_ohlcv()` Synthetic Data

**Generalisiert** (claude-trader-Schema wird ergaenzt, Code wandert spaeter ggf. in `ct_core/`):
- `candles`-Tabelle bekommt zusaetzliche Spalten `asset_type` und `exchange` (siehe DB-Schema unten)
- `fetcher.insert_candles_batch()` schreibt diese Spalten mit (Default `crypto`/`binance`, fuer claude-trader unveraendert)

---

## DB-Schema-Erweiterungen

### Aenderungen am bestehenden `claude-trader/ct/db/schema.sql` (additiv, ruekwaertskompatibel)

```sql
-- Multi-Asset-Support (DEFAULT macht claude-trader-Verhalten unveraendert)
ALTER TABLE candles ADD COLUMN IF NOT EXISTS asset_type TEXT NOT NULL DEFAULT 'crypto';
ALTER TABLE candles ADD COLUMN IF NOT EXISTS exchange TEXT;
CREATE INDEX IF NOT EXISTS idx_candles_asset_type ON candles (asset_type, symbol, interval, time DESC);
```

### Neue Tabellen in `portfolio/pt/db/schema_portfolio.sql`

```sql
-- Asset-Master (Metadata pro Symbol — geteilt mit claude-trader nutzbar)
CREATE TABLE assets (
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,        -- crypto, stock, etf, fx, commodity, bond
    exchange        TEXT,                  -- binance, nasdaq, xetra, lse, etc.
    name            TEXT NOT NULL,
    isin            TEXT,
    wkn             TEXT,
    currency        TEXT NOT NULL,         -- USD, EUR, CHF, BTC...
    sector          TEXT,
    region          TEXT,
    metadata        JSONB,                 -- ETF-X-Ray, Coingecko-ID, Logo-URL
    PRIMARY KEY (symbol, asset_type)
);

-- Portfolios (User kann mehrere Portfolios haben, z.B. "Real-Depot" + "Watch")
CREATE TABLE portfolios (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT,                  -- NULL = single-user (heute), Multi-User-ready
    name            TEXT NOT NULL,
    base_currency   TEXT NOT NULL DEFAULT 'EUR',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at     TIMESTAMPTZ
);

-- Transactions = einzige Source-of-Truth (Holdings sind aggregiert daraus)
CREATE TABLE transactions (
    id              BIGSERIAL PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id),
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    action          TEXT NOT NULL,         -- buy, sell, dividend, split, fee, transfer_in, transfer_out, deposit, withdrawal
    executed_at     TIMESTAMPTZ NOT NULL,
    quantity        NUMERIC(28,12) NOT NULL,    -- Decimal-tauglich
    price           NUMERIC(20,8) NOT NULL,     -- in trade_currency
    trade_currency  TEXT NOT NULL,
    fees            NUMERIC(20,8) NOT NULL DEFAULT 0,
    fees_currency   TEXT,
    fx_rate         NUMERIC(20,10),             -- bei FX-Trades
    note            TEXT,
    source          TEXT NOT NULL,              -- pdf:trade_republic, csv:binance, manual, broker_api:alpaca
    source_doc_id   TEXT,                       -- Hash des Original-PDFs/CSVs
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,                -- Soft-Delete fuer Audit
    UNIQUE (portfolio_id, source, source_doc_id, executed_at, symbol, action, quantity)
);

CREATE INDEX idx_tx_portfolio_time ON transactions (portfolio_id, executed_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_tx_symbol ON transactions (symbol, asset_type, executed_at DESC) WHERE deleted_at IS NULL;

-- Audit-Trail (jede Aenderung an Transactions immutable)
CREATE TABLE transaction_audit (
    id              BIGSERIAL PRIMARY KEY,
    transaction_id  BIGINT NOT NULL REFERENCES transactions(id),
    operation       TEXT NOT NULL,         -- INSERT, UPDATE, DELETE
    old_data        JSONB,
    new_data        JSONB,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by      TEXT
);

-- Corporate Actions (Splits, Dividends, Spinoffs — wendet sich auf Transactions an)
CREATE TABLE corporate_actions (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    action_type     TEXT NOT NULL,         -- split, reverse_split, dividend, spinoff, symbol_change, merger
    ex_date         DATE NOT NULL,
    pay_date        DATE,
    ratio_from      NUMERIC(20,10),        -- 1 (alt) -> 4 (neu) bei AAPL 4:1
    ratio_to        NUMERIC(20,10),
    cash_amount     NUMERIC(20,8),
    cash_currency   TEXT,
    new_symbol      TEXT,                  -- bei symbol_change/spinoff
    metadata        JSONB,
    source          TEXT NOT NULL,         -- finnhub, eodhd, manual
    UNIQUE (symbol, asset_type, action_type, ex_date)
);

-- Tagessnapshots (vorberechnete Performance fuer schnelles Dashboard)
CREATE TABLE portfolio_snapshots (
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id),
    snapshot_date   DATE NOT NULL,
    total_value     NUMERIC(20,8) NOT NULL,        -- in base_currency
    total_cost_basis NUMERIC(20,8) NOT NULL,
    realized_pnl    NUMERIC(20,8) NOT NULL,
    unrealized_pnl  NUMERIC(20,8) NOT NULL,
    cash            NUMERIC(20,8) NOT NULL,
    holdings_count  INTEGER NOT NULL,
    metadata        JSONB,                          -- per-asset Breakdown
    PRIMARY KEY (portfolio_id, snapshot_date)
);
SELECT create_hypertable('portfolio_snapshots', 'snapshot_date', if_not_exists => TRUE);

-- News pro Asset (gecached, daily refresh)
CREATE TABLE asset_news (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    published_at    TIMESTAMPTZ NOT NULL,
    source          TEXT NOT NULL,         -- marketaux, finnhub, coingecko
    title           TEXT NOT NULL,
    summary         TEXT,
    url             TEXT NOT NULL,
    sentiment       NUMERIC(4,3),          -- -1.0 bis +1.0
    metadata        JSONB,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, url)
);
CREATE INDEX idx_news_symbol_time ON asset_news (symbol, asset_type, published_at DESC);

-- AI-Insights pro Asset (LLM-generiert, gecached)
CREATE TABLE asset_insights (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    insight_type    TEXT NOT NULL,         -- earnings_summary, sentiment_summary, theme, risk
    content         TEXT NOT NULL,
    model           TEXT NOT NULL,         -- openrouter:claude-opus-4-7 etc.
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until     TIMESTAMPTZ NOT NULL,  -- TTL fuer Refresh
    metadata        JSONB
);
CREATE INDEX idx_insights_symbol ON asset_insights (symbol, asset_type, generated_at DESC);

-- FX-Raten (taeglich, ECB/Frankfurter)
-- Wir nutzen die existierende market_meta-Tabelle: source='frankfurter', symbol='EURUSD' etc.

-- Import-Log (jedes hochgeladene PDF/CSV mit Hash)
CREATE TABLE import_log (
    id              BIGSERIAL PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id),
    file_name       TEXT NOT NULL,
    file_hash       TEXT NOT NULL,
    file_type       TEXT NOT NULL,         -- pdf, csv
    parser          TEXT NOT NULL,         -- trade_republic, scalable, etc.
    transactions_added INTEGER NOT NULL,
    transactions_skipped INTEGER NOT NULL,
    raw_text        TEXT,                  -- fuer Debug
    parsed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (portfolio_id, file_hash)
);
```

---

## Daten-Pipeline (Multi-Asset Fetcher)

### Strategie: Cache-First, On-Demand-Fill, Daily-Sync

| Asset-Klasse | Primary | Backup | Rate-Limit | Cache-TTL |
|-------------|---------|--------|------------|-----------|
| Crypto | CoinGecko (free) | Binance (existing) | 10 req/s free | Live-Preis 1min, Historisch in DB |
| Stocks/ETFs | Twelve Data (800/day free) | EOD Historical (€20/mo opt.) | 8/min | Live 5min, EOD in DB |
| FX | Frankfurter (ECB, free, unlimited) | exchangerate.host | unlimited | EOD in DB |
| News | Marketaux + Finnhub | NewsAPI | 100/day free | 24h |
| Corporate Actions | Finnhub | EODHD | siehe oben | wochentlich Sync |
| Earnings | Finnhub | manual | siehe oben | quartalsweise |

### Neue Fetcher-Module (nach Pattern von [claude-trader/ct/data/binance.py](claude-trader/ct/data/binance.py))

Jeder Fetcher liefert OHLCV-Tuples kompatibel zu `insert_candles_batch()`. Beispiel-Signatur:

```python
async def fetch_coingecko_ohlcv(coin_id: str, vs_currency: str, days: int) -> list[dict]:
    """Returns list of {time, symbol, interval, open, high, low, close, volume, asset_type='crypto', exchange='coingecko'}."""
```

### Sync-CLI

```bash
pt sync prices              # alle Holdings refresh (incremental)
pt sync prices --full       # voller Backfill
pt sync news                # News fuer alle Holdings (24h-TTL)
pt sync corp-actions        # Splits/Dividends fuer alle Holdings
pt sync fx                  # FX-Raten ECB
pt sync insights            # LLM-Insights regenerieren (nur stale)
pt sync all                 # Komplett-Sync (cron-ready)
```

---

## PDF/CSV-Import (Kern-Eingabeweg)

**WARTET AUF**: User-PDF-Beispiel — die Parser-Spezifikation wird darauf zugeschnitten. Annahmen unten basieren auf dokumentierten Trade-Republic/Scalable-Statement-Formaten.

### Architektur

```
ImportWizard (Frontend)
    └─ POST /api/import/upload (PDF/CSV)
        └─ format_detect.py → erkennt Broker via Header/Logo/Layout
            └─ parser/<broker>.py → extrahiert Transaction-Liste
                └─ Validation (Schema, Duplikate via source_doc_id)
                    └─ Transactions-INSERT + Audit-Trail
                        └─ Reconciliation gegen letzten Snapshot-Wert
```

### Library-Wahl

- **PDF**: `pdfplumber` (table-extraction, layout-preserving) — bewaehrt fuer deutsche Broker
- **CSV**: `pandas` mit Format-Mapping-YAML pro Exchange

### Parser-Roadmap

1. **User-PDF analysieren** (sobald geliefert) → erster Parser
2. **Trade Republic** (PDF-Quartalsberichte + Bestaetigungen)
3. **Scalable Capital** (PDF-Depotauszug)
4. **Coinbase** (CSV-Export)
5. **Binance** (CSV-Export, schon teilweise via existing claude-trader-API verfuegbar)
6. **Generic-Mapper** (Mapping-UI im Frontend, fuer unbekannte Formate)

### Idempotenz

- Jeder Import berechnet `sha256(file_bytes)` als `source_doc_id`
- `transactions.UNIQUE (portfolio_id, source, source_doc_id, executed_at, symbol, action, quantity)` — selbes PDF zweimal hochladen → 0 neue Transactions

---

## Performance-Engine (das Herz von "100% korrekte Zahlen")

### Money-Math Hard-Rules

1. **Niemals `float`** fuer Geldbetraege im Code → immer `decimal.Decimal` (28-stellig) oder `NUMERIC(20,8)` in DB
2. **Rounding nur beim Display**, nie in Storage oder Zwischenschritten
3. **FX-Konvertierung** nur ueber gespeicherte historische Raten (ECB/Frankfurter), nie Live-Raten fuer historische Werte
4. **Reconciliation-Test** gegen Excel-XIRR & CFA-Reference-Cases vor jedem Release

### Implementierte Metriken

| Metrik | Modul | Referenz-Implementierung |
|--------|-------|--------------------------|
| Time-Weighted Return (TWR) | [pt/performance/twr.py](portfolio/pt/performance/twr.py) | Sub-Period Chaining bei Cash-Flows |
| Money-Weighted Return (XIRR) | [pt/performance/mwr.py](portfolio/pt/performance/mwr.py) | Newton-Raphson + Bisection-Fallback |
| CAGR | [pt/performance/metrics.py](portfolio/pt/performance/metrics.py) | annualisiert |
| YTD / 1Y / 3Y / 5Y / 10Y | [pt/performance/metrics.py](portfolio/pt/performance/metrics.py) | rollende Returns |
| Sharpe / Sortino | [pt/performance/metrics.py](portfolio/pt/performance/metrics.py) | mit Risk-Free-Rate aus ECB |
| Max Drawdown / Calmar | [pt/performance/metrics.py](portfolio/pt/performance/metrics.py) | peak-to-trough |
| Volatility | [pt/performance/metrics.py](portfolio/pt/performance/metrics.py) | annualisiert (252/365) |
| Cost-Basis FIFO/LIFO/Avg/SpecID | [pt/performance/cost_basis.py](portfolio/pt/performance/cost_basis.py) | Tax-Lots-Tracking |
| Benchmark-Vergleich | [pt/performance/benchmarks.py](portfolio/pt/performance/benchmarks.py) | S&P500, MSCI World, Custom-Mix |
| Realized vs Unrealized | [pt/tax/realize.py](portfolio/pt/tax/realize.py) | Lot-by-Lot Matching |

### Korrektheits-Garantien (Regression-geschuetzt)

- **Reference-Test-Suite**: jede Formel hat Unit-Tests gegen
  - Excel-XIRR (5 hand-berechnete Cases)
  - CFA Institute Beispiele (TWR vs MWR Standard-Cases)
  - Sharesight-Beispieldaten (oeffentliche Help-Docs)
- **Property-Tests** mit `hypothesis`: TWR(only-1-cashflow) = simple-return
- **Reconciliation gegen Broker-Statement**: nightly Job, Diff-Report bei > 0.1% Abweichung

---

## News & Insights (Differentiator)

### News-Layer
- **Marketaux** (free 100 req/day): financial news aggregation, sentiment built-in
- **Finnhub** (free): per-symbol news, Earnings-Calendar
- **CoinGecko** (free): Crypto-News, Trending
- Caching: `asset_news`-Tabelle mit 24h-Refresh

### LLM-Insights (reuse claude-trader OpenRouter-Setup)

| Insight | Trigger | Modell | Cache |
|---------|---------|--------|-------|
| Earnings-Summary | nach Earnings-Call (Finnhub Calendar) | Sonnet 4.6 | bis naechste Earnings |
| Asset-Outlook | weekly cron | Opus 4.7 (1M context bei vielen News) | 7 Tage |
| Theme-Detection | nach Sync, wenn 3+ Holdings gleichzeitig stark bewegen | Sonnet 4.6 | 24h |
| Risk-Alert | bei MaxDD > X% oder Vola-Spike | Sonnet 4.6 | bis Trigger geloest |

OpenRouter-API-Key bereits in [claude-trader/.env](claude-trader/.env) — wird via shared `.env`-Symlink genutzt.

---

## Frontend (Weltklasse-UX)

### Pages (10 Hauptseiten)

| Seite | Zweck | Killer-Element |
|-------|-------|----------------|
| Dashboard | Sofort-Ueberblick in 3s | Net-Worth-Card mit Tages-Delta, Top-3-Movers, Mini-Sparkline-Chart, "since last open"-Badge |
| Holdings | Tabelle aller Positionen | Filter (Asset-Typ, Region, Sector), Sort, Drill-down, Realized/Unrealized Toggle |
| AssetDetail | Tiefe Analyse pro Asset | TradingView-style Chart + News-Feed + LLM-Insight-Card + Dividenden-Historie + Trader-Bridge-Signal-Box |
| Performance | TWR/MWR Charts ueber Zeit | Toggle TWR vs MWR, vs Benchmarks (S&P500, MSCI World), Period-Selector (1W..MAX) |
| Allocation | Pie + Sunburst | Drillbar (Asset-Klasse → Region → Sector → Position), Target vs Actual, Drift-Indikator |
| Transactions | Audit-Log + Editor | Filter, Edit/Delete (mit Audit-Trail-Anzeige), Source-PDF-Download |
| Income | Dividenden-Kalender | Forecast naechste 12 Monate, History, Tax-Status |
| News & Insights | Feed pro Holdings | Sentiment-Heatmap, AI-Daily-Brief am Morgen |
| Tax | Realized/Unrealized | DE-Format-Export, Spekulationsfrist-Anzeige (Crypto 1 Jahr, Stocks Abgeltung) |
| Settings | Brokers, Currencies, APIs | API-Keys, Base-Currency, Cron-Jobs, Theme |

### UX-Prinzipien (aus Marktstudie ueberlegen)

1. **3-Sekunden-Regel**: Dashboard zeigt in 3 Sekunden alle wichtigen Zahlen
2. **Color-Coding konsistent**: Green = Gain, Red = Loss, Gray = Flat, Blue = Info, Amber = Warning
3. **Decimal-Precision** angemessen: Portfolio-Wert immer 2 Stellen, Crypto-Quantitaet 8 Stellen, FX 4 Stellen
4. **Dark-Mode-First**, Light-Mode toggle-bar
5. **Mobile-Responsive**: alle Pages funktional auf Smartphone (kein PWA in Phase 1, aber responsive)
6. **Loading-States**: Skeleton-Screens, niemals leere Spinner > 500ms
7. **Microinteractions**: Hover-Effects, Toast-Notifications (bottom-right), smooth-Transitions

---

## Trader-Bridge (claude-trader-Integration)

### Phase-1: claude-trader liest Portfolio (read-only)

Endpoints in `pt/api/routes/`:
- `GET /api/holdings/symbols` — Liste aller getrackter Symbole
- `GET /api/holdings/{symbol}` — Position-Details (qty, cost-basis, unrealized P&L)

claude-trader's Monitor-Agent kann dann z.B. asset-spezifische Empfehlungen geben:
> "Du haeltst 2.5 ETH @ EUR 2,800 cost-basis. Aktueller Preis EUR 3,200 (+14%). Bot-Empfehlung: HOLD (Trend-Up confirmed, Vola-low)."

### Phase-2: Portfolio liest claude-trader-Signals

Im AssetDetail.tsx eine "Trader-Bot-Box":
- **Heutiges Signal**: BUY/HOLD/SELL + Confidence
- **Historie**: Was haette der Bot gerade gesagt zu meinem Kauf-Zeitpunkt? Was waere passiert?
- **What-if**: "Haette ich Bot-Signal gefolgt, waere mein Return um X% besser/schlechter"

API-Aufruf: `GET claude-trader://api/predict/{symbol}` (intern, ueber Docker-Network).

---

## CLI (`pt`)

Analog zu `ct` (claude-trader). Typer-basiert.

```bash
pt --help
pt portfolio create "Real-Depot" --base-currency EUR
pt holdings list                                     # rich-Tabelle
pt holdings show AAPL --period 1Y
pt import file ~/Downloads/depot-2026-04.pdf         # auto-detect
pt import dry-run ~/Downloads/depot.pdf              # preview vor Insert
pt sync all                                          # alle APIs refresh
pt perf summary --period YTD
pt perf metrics --benchmark sp500
pt tax realized --year 2025 --format de-est
pt audit reconcile --since 2025-01-01                # diff Broker vs Calc
pt serve                                             # FastAPI + Vite (dev)
```

---

## Verification (End-to-End-Test der Korrektheit)

### Stufe 1: Unit-Tests (vor jedem Commit)
```bash
cd portfolio && pytest tests/test_twr.py tests/test_mwr.py tests/test_cost_basis.py tests/test_corp_actions.py tests/test_fx.py
```
Alle Performance-Formeln gegen Reference-Cases (Excel/CFA).

### Stufe 2: Integration-Tests (CI)
- Mock-Server fuer CoinGecko/Twelve Data/Frankfurter
- Synthetic-Portfolio-Workflow: 5 Trades simuliert → erwartetes TWR/MWR exakt matchen
- PDF-Parser-Tests gegen Beispiel-PDFs (User-PDF + 2 weitere als Fixtures)

### Stufe 3: Reconciliation (post-MVP, nightly)
```bash
pt audit reconcile --since 2025-01-01
```
Vergleich Portfolio-Berechnung vs Broker-Statement-Wert. Diff > 0.1% → Slack/E-Mail-Alert (spaeter via existing claude-trader Alert-Engine).

### Stufe 4: Manuelle Verification (User)
1. PDF von Broker hochladen → Holdings sichtbar?
2. Performance gegen Broker-App vergleichen → Abweichung dokumentiert + erklaert?
3. Stock-Split-Asset (z.B. NVDA 10:1 in 2024) → Quantity korrekt skaliert?
4. Multi-Currency-Asset (US-Stock im EUR-Depot) → Konvertierungen ueber Zeit korrekt?

---

## Implementierungs-Phasen (geschaetzte Aufwaende)

| Phase | Inhalt | Tage | Erfolg = |
|-------|--------|------|---------|
| **0** | Repo-Bootstrap, `.cortex.json`, pyproject, docker-compose, Symlinks zu claude-trader | 1 | `pt --version` laeuft |
| **1** | DB-Schema (ALTER candles + 9 neue Tables), Asset-Master-Sync (CoinGecko + Twelve Data) | 2-3 | `pt sync prices` schreibt Multi-Asset-Candles |
| **2** | Performance-Engine (TWR, MWR, Cost-Basis, alle Metriken) **mit Reference-Tests** | 4-5 | alle Formeln gruen gegen Excel/CFA |
| **3** | PDF-Importer (User-PDF zuerst, dann TR + Scalable) + Validation + Audit | 4-5 | User-PDF → korrekte Transactions in DB |
| **4** | FastAPI-Routes (holdings, performance, transactions, news) + CLI (`pt`) | 3-4 | API liefert volle Portfolio-Sicht |
| **5** | Frontend-MVP (Dashboard, Holdings, AssetDetail, Performance, Transactions) | 6-8 | klickbarer Prototyp, alle Zahlen live |
| **6** | News + LLM-Insights + Sentiment | 3-4 | Per-Asset-News + Earnings-Summary live |
| **7** | Tax (FIFO + DE-Reports) + Reconciliation-Job | 3-4 | `pt tax realized --year 2025` produziert valides Dokument |
| **8** | Allocation, Income, Settings, Polish, Mobile-Responsive | 4-6 | alle 10 Pages, UX-Review |
| **9** | Trader-Bridge (claude-trader read-only Endpoints + Frontend-Box) | 2-3 | Bot-Signal pro Holding sichtbar |

**Total Zeit-Schaetzung**: 32-43 Arbeitstage. Realistisch in 2-3 Monaten Teilzeit.

---

## Critical Files (Referenzen)

### claude-trader (zu lesen / wiederzuverwenden)
- [claude-trader/ct/db/schema.sql](claude-trader/ct/db/schema.sql) — Basis-Schema (wird erweitert)
- [claude-trader/ct/db/connection.py](claude-trader/ct/db/connection.py) — psycopg-Wrapper (reuse)
- [claude-trader/ct/data/fetcher.py](claude-trader/ct/data/fetcher.py:54) — `insert_candles_batch()` (reuse)
- [claude-trader/ct/data/binance.py](claude-trader/ct/data/binance.py) — async-HTTP-Pattern (reuse als Template)
- [claude-trader/ct/api/app.py](claude-trader/ct/api/app.py) — FastAPI-Struktur (reuse als Template)
- [claude-trader/ct/cli.py](claude-trader/ct/cli.py) — Typer-Sub-App-Pattern (reuse)
- [claude-trader/tests/conftest.py](claude-trader/tests/conftest.py) — Synthetic-OHLCV-Fixtures (reuse)
- [claude-trader/docker-compose.yml](claude-trader/docker-compose.yml) — TimescaleDB-Setup (shared)
- [claude-trader/.env](claude-trader/.env) — DB-Credentials + OpenRouter-Key (shared)
- [claude-trader/frontend/package.json](claude-trader/frontend/package.json) — Frontend-Stack (Vorbild)

### portfolio (zu erstellen)
- `portfolio/pt/db/schema_portfolio.sql` (9 neue Tabellen, siehe oben)
- `portfolio/pt/data/coingecko.py`, `twelve_data.py`, `frankfurter.py`, `marketaux.py`, `finnhub.py`
- `portfolio/pt/importers/pdf/<broker>.py` (mehrere)
- `portfolio/pt/performance/{twr,mwr,metrics,cost_basis,benchmarks}.py`
- `portfolio/pt/api/app.py` + `routes/`
- `portfolio/pt/cli.py` + `cli_*.py`
- `portfolio/frontend/src/pages/*.tsx`
- `portfolio/tests/test_*.py`

---

## Was fuer das "Weltklasse"-Versprechen kritisch ist

Aus der Marktstudie destilliert — **wenn auch nur eines davon fehlt, ist es nur "noch ein Tracker":**

1. **100% korrekte Zahlen** — Decimal-Math, Reference-Tests, Reconciliation
2. **Auto-Corporate-Actions** — Splits/Dividends nicht manuell
3. **Multi-Asset wirklich ein Tool** — nicht "Crypto in einer Tab, Stocks in anderer"
4. **Performance-Metriken vollstaendig** — TWR + MWR sichtbar, nicht nur "Total Return"
5. **3-Sekunden-Dashboard** — kein "lade 8 Sekunden bis ich was sehe"
6. **News + Insights pro Asset** — nicht abstrakte News-Liste, sondern relevante Stories
7. **Audit-Trail** — jede Transaction-Historie nachvollziehbar
8. **PDF-Import "just works"** — User soll sich nicht mit Mapping rumschlagen muessen
9. **Multi-Currency korrekt** — historische FX, nicht Live-Rate
10. **Mobile-tauglich** — Portfolio checken im Cafe muss gehen

---

## Offene Punkte (Klaerungsbedarf vor Phase 3)

1. **User-PDF Format**: Beispiel-PDF zur Format-Detection abwarten — bestimmt 1. Parser
2. **Steuern-Detail**: DE Abgeltungssteuer einfacher (25% pauschal), Crypto-Spekulationsfrist 1 Jahr — wieviel Compliance-Nahe wollen wir? Reicht "tax-relevant Brutto-Werte fuer Steuer-Software" (DATEV/SteuerGo) oder direkt finales Formular?
3. **Hosting-Plan**: bleibt lokal? Oder spaeter Cloud-Deploy (Hetzner/Railway/Fly.io)?
4. **Nutzung claude-trader-OpenRouter-Key**: shared `.env` ok, oder eigener Key fuer portfolio?

Diese werden waehrend der Implementierung adressiert — nicht blockierend fuer Plan-Approval.
