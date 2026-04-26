-- Minimal public-schema bootstrap for the standalone deployment.
--
-- When the portfolio runs against a brand-new TimescaleDB (i.e. NOT shared
-- with claude-trader), nothing has created the `public.candles` and
-- `public.market_meta` hypertables yet. This file is loaded once via the
-- TimescaleDB image's /docker-entrypoint-initdb.d/ mechanism on first
-- container start (when the data volume is empty).
--
-- The portfolio's own schema_portfolio.sql is mounted at 02_*.sql and
-- runs immediately after — its ALTER TABLE candles ADD COLUMN steps
-- depend on `public.candles` existing first.
--
-- Keep this in sync with the columns claude-trader writes — when their
-- schema.sql gains a new column we depend on, mirror it here too.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS public.candles (
    time             TIMESTAMPTZ NOT NULL,
    symbol           TEXT NOT NULL,
    interval         TEXT NOT NULL,
    open             DOUBLE PRECISION NOT NULL,
    high             DOUBLE PRECISION NOT NULL,
    low              DOUBLE PRECISION NOT NULL,
    close            DOUBLE PRECISION NOT NULL,
    volume           DOUBLE PRECISION NOT NULL,
    trades           INTEGER,
    source           TEXT NOT NULL DEFAULT 'binance',
    taker_buy_volume DOUBLE PRECISION,
    PRIMARY KEY (time, symbol, interval)
);
SELECT create_hypertable('public.candles', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_interval_time
    ON public.candles (symbol, interval, time DESC);

CREATE TABLE IF NOT EXISTS public.market_meta (
    time     TIMESTAMPTZ NOT NULL,
    source   TEXT NOT NULL,
    symbol   TEXT NOT NULL DEFAULT '',
    value    DOUBLE PRECISION NOT NULL,
    metadata JSONB,
    PRIMARY KEY (time, source, symbol)
);
SELECT create_hypertable('public.market_meta', 'time', if_not_exists => TRUE);
