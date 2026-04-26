-- Portfolio Tracker — Schema Extensions
-- Run AFTER claude-trader's schema.sql is applied to the same database.
--
-- Strategy:
--   - Public schema: candles, market_meta (shared with claude-trader, augmented with asset_type/exchange)
--   - "portfolio" schema: holdings, transactions, audit, news, insights, snapshots
--
-- All money columns use NUMERIC for exact decimal arithmetic — never DOUBLE for prices/values.
-- All DDL is idempotent (IF NOT EXISTS / DO blocks for ALTERs).

-- =============================================================================
-- 1) candles table augmentation (in public schema, used by both repos)
-- =============================================================================

DO $$ BEGIN
    ALTER TABLE public.candles ADD COLUMN asset_type TEXT NOT NULL DEFAULT 'crypto';
EXCEPTION WHEN duplicate_column THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.candles ADD COLUMN exchange TEXT;
EXCEPTION WHEN duplicate_column THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_candles_asset_type
    ON public.candles (asset_type, symbol, interval, time DESC);


-- =============================================================================
-- 2) Portfolio schema
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS portfolio;
SET search_path TO portfolio, public;


-- Asset-Master: Metadata pro Symbol (geteilt nutzbar von claude-trader)
CREATE TABLE IF NOT EXISTS portfolio.assets (
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,            -- crypto, stock, etf, fx, commodity, bond
    exchange        TEXT,                      -- binance, nasdaq, xetra, lse, etc.
    name            TEXT NOT NULL,
    isin            TEXT,
    wkn             TEXT,
    currency        TEXT NOT NULL,             -- USD, EUR, CHF, BTC...
    sector          TEXT,
    region          TEXT,
    metadata        JSONB,                     -- ETF-X-Ray, Coingecko-ID, Logo-URL
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, asset_type)
);
CREATE INDEX IF NOT EXISTS idx_assets_isin ON portfolio.assets (isin) WHERE isin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_assets_wkn  ON portfolio.assets (wkn)  WHERE wkn  IS NOT NULL;


-- Portfolios: User kann mehrere haben (z.B. "Real-Depot" + "Watchlist")
CREATE TABLE IF NOT EXISTS portfolio.portfolios (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT,                      -- NULL = single-user, multi-user-ready
    name            TEXT NOT NULL,
    base_currency   TEXT NOT NULL DEFAULT 'EUR',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at     TIMESTAMPTZ
);


-- Transactions = einzige Source-of-Truth (Holdings sind aggregiert daraus)
CREATE TABLE IF NOT EXISTS portfolio.transactions (
    id              BIGSERIAL PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolio.portfolios(id),
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    action          TEXT NOT NULL,             -- buy, sell, dividend, split, fee, transfer_in, transfer_out, deposit, withdrawal
    executed_at     TIMESTAMPTZ NOT NULL,
    quantity        NUMERIC(28,12) NOT NULL,
    price           NUMERIC(20,8) NOT NULL,    -- in trade_currency
    trade_currency  TEXT NOT NULL,
    fees            NUMERIC(20,8) NOT NULL DEFAULT 0,
    fees_currency   TEXT,
    fx_rate         NUMERIC(20,10),            -- fuer FX-Konvertierung im Trade-Moment
    note            TEXT,
    source          TEXT NOT NULL,             -- pdf:trade_republic, csv:binance, manual, ...
    source_doc_id   TEXT,                      -- Hash des Original-Dokuments
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tx_dedupe
    ON portfolio.transactions (portfolio_id, source, source_doc_id, executed_at, symbol, action, quantity)
    WHERE source_doc_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_tx_portfolio_time
    ON portfolio.transactions (portfolio_id, executed_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_tx_symbol
    ON portfolio.transactions (symbol, asset_type, executed_at DESC)
    WHERE deleted_at IS NULL;


-- Audit-Trail: jede Aenderung an Transactions immutable festhalten
CREATE TABLE IF NOT EXISTS portfolio.transaction_audit (
    id              BIGSERIAL PRIMARY KEY,
    transaction_id  BIGINT NOT NULL REFERENCES portfolio.transactions(id),
    operation       TEXT NOT NULL,             -- INSERT, UPDATE, DELETE
    old_data        JSONB,
    new_data        JSONB,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by      TEXT
);
CREATE INDEX IF NOT EXISTS idx_tx_audit_tx
    ON portfolio.transaction_audit (transaction_id, changed_at DESC);


-- Corporate Actions: Splits, Dividends, Spinoffs (auto-applied auf Transactions)
CREATE TABLE IF NOT EXISTS portfolio.corporate_actions (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    action_type     TEXT NOT NULL,             -- split, reverse_split, dividend, spinoff, symbol_change, merger
    ex_date         DATE NOT NULL,
    pay_date        DATE,
    ratio_from      NUMERIC(20,10),
    ratio_to        NUMERIC(20,10),
    cash_amount     NUMERIC(20,8),
    cash_currency   TEXT,
    new_symbol      TEXT,
    metadata        JSONB,
    source          TEXT NOT NULL,             -- finnhub, eodhd, manual
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_corp_action
    ON portfolio.corporate_actions (symbol, asset_type, action_type, ex_date);
CREATE INDEX IF NOT EXISTS idx_corp_symbol
    ON portfolio.corporate_actions (symbol, asset_type, ex_date DESC);


-- Tagessnapshots: vorberechnete Performance fuer schnelles Dashboard
CREATE TABLE IF NOT EXISTS portfolio.portfolio_snapshots (
    portfolio_id    INTEGER NOT NULL REFERENCES portfolio.portfolios(id),
    snapshot_date   DATE NOT NULL,
    total_value     NUMERIC(20,8) NOT NULL,        -- FX-naive sum of qty x close in source currencies
    total_cost_basis NUMERIC(20,8) NOT NULL,
    realized_pnl    NUMERIC(20,8) NOT NULL,
    unrealized_pnl  NUMERIC(20,8) NOT NULL,
    cash            NUMERIC(20,8) NOT NULL,
    holdings_count  INTEGER NOT NULL,
    metadata        JSONB,
    PRIMARY KEY (portfolio_id, snapshot_date)
);
-- FX-aware base-currency total. NULL when at least one source currency
-- has no historical Frankfurter rate at-or-before snapshot_date.
DO $$ BEGIN
    ALTER TABLE portfolio.portfolio_snapshots
        ADD COLUMN total_value_base NUMERIC(20,8);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
-- TimescaleDB-Hypertable (geht nur fuer eine Tabelle ohne Foreign-Keys auf andere
-- Hypertables; falls FK-Konflikt: regulaere Tabelle reicht voellig fuer Snapshots).
DO $$ BEGIN
    PERFORM create_hypertable('portfolio.portfolio_snapshots', 'snapshot_date', if_not_exists => TRUE);
EXCEPTION WHEN OTHERS THEN
    -- Fall back to regular table if hypertable creation fails (FK constraint, etc.)
    RAISE NOTICE 'portfolio_snapshots: regular table (hypertable creation skipped: %)', SQLERRM;
END $$;


-- News pro Asset (gecached, daily refresh via `pt sync news`)
CREATE TABLE IF NOT EXISTS portfolio.asset_news (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    published_at    TIMESTAMPTZ NOT NULL,
    source          TEXT NOT NULL,             -- marketaux, finnhub, coingecko
    title           TEXT NOT NULL,
    summary         TEXT,
    url             TEXT NOT NULL,
    sentiment       NUMERIC(4,3),              -- -1.0 bis +1.0
    metadata        JSONB,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_news_url ON portfolio.asset_news (source, url);
CREATE INDEX IF NOT EXISTS idx_news_symbol_time
    ON portfolio.asset_news (symbol, asset_type, published_at DESC);


-- AI-Insights pro Asset (LLM-generiert, gecached mit TTL)
CREATE TABLE IF NOT EXISTS portfolio.asset_insights (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    insight_type    TEXT NOT NULL,             -- earnings_summary, sentiment_summary, theme, risk
    content         TEXT NOT NULL,
    model           TEXT NOT NULL,             -- openrouter:claude-opus-4-7 etc.
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until     TIMESTAMPTZ NOT NULL,
    metadata        JSONB
);
CREATE INDEX IF NOT EXISTS idx_insights_symbol
    ON portfolio.asset_insights (symbol, asset_type, generated_at DESC);


-- Import-Log: jedes hochgeladene Dokument mit Hash (Idempotenz)
CREATE TABLE IF NOT EXISTS portfolio.import_log (
    id              BIGSERIAL PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolio.portfolios(id),
    file_name       TEXT NOT NULL,
    file_hash       TEXT NOT NULL,
    file_type       TEXT NOT NULL,             -- pdf, csv
    parser          TEXT NOT NULL,             -- trade_republic, scalable, etc.
    transactions_added   INTEGER NOT NULL,
    transactions_skipped INTEGER NOT NULL,
    raw_text        TEXT,
    parsed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_import_log
    ON portfolio.import_log (portfolio_id, file_hash);


-- =============================================================================
-- 3) Audit Trigger — every write to transactions logged immutably
-- =============================================================================

-- Audit trigger: INSERT and UPDATE only.
-- DELETE is intentionally not audited because:
--   1) Production code uses soft-delete (UPDATE deleted_at) — already captured.
--   2) Hard-DELETE is test-cleanup / admin-only and the audit-FK would block it.
-- If hard-DELETE is ever needed in production, drop the FK or cascade explicitly.
CREATE OR REPLACE FUNCTION portfolio.fn_log_transaction_audit() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO portfolio.transaction_audit (transaction_id, operation, new_data, changed_by)
        VALUES (NEW.id, 'INSERT', to_jsonb(NEW), current_setting('portfolio.changed_by', true));
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO portfolio.transaction_audit (transaction_id, operation, old_data, new_data, changed_by)
        VALUES (NEW.id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW), current_setting('portfolio.changed_by', true));
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_transactions_audit ON portfolio.transactions;
CREATE TRIGGER trg_transactions_audit
    AFTER INSERT OR UPDATE ON portfolio.transactions
    FOR EACH ROW EXECUTE FUNCTION portfolio.fn_log_transaction_audit();
