# Database

TimescaleDB on port 5434, shared with claude-trader. Connection helper
[`pt/db/connection.py`](../../pt/db/connection.py) sets `search_path` to
`portfolio, public` so unqualified names hit the right schema.

## Schemas

- `public` — owned by claude-trader. We add to it (additively) but never break it.
- `portfolio` — owned by us. All app tables live here.

## Tables

### public (shared with claude-trader)

| Table | Purpose | Our augmentation |
|--|--|--|
| `candles` | OHLCV hypertable, primary key `(time, symbol, interval)` | `asset_type` (DEFAULT `'crypto'`) + `exchange` columns + index on those |
| `market_meta` | Fear&Greed, funding rates, FX rates etc. | We write FX with `source='frankfurter'`, symbol like `'EURUSD'` |

### portfolio (ours)

| Table | What lives here | Notes |
|--|--|--|
| `assets` | Asset master metadata: name, ISIN, WKN, sector, region, currency | PK `(symbol, asset_type)` — `find_similar()` does fuzzy lookup |
| `portfolios` | One row per user portfolio | `user_id` is `NULL`-able for now (single-user); `archived_at` for soft-archive |
| `transactions` | Buy / sell / dividend / split / fee / transfer / deposit / withdrawal | NUMERIC(28,12) for qty, NUMERIC(20,8) for price/fees. **Source of truth.** |
| `transaction_audit` | INSERT/UPDATE history on transactions | Populated by trigger; FK to transactions |
| `corporate_actions` | Splits, dividends, spinoffs, symbol changes | Not yet auto-applied to transactions |
| `portfolio_snapshots` | Pre-computed daily values | Hypertable on `snapshot_date`; not yet generated |
| `asset_news` | Cached news from Finnhub / Marketaux / ... | Idempotent on `(source, url)` |
| `asset_insights` | LLM-generated insights with TTL via `valid_until` | Not yet populated — see `news-insights.md` |
| `import_log` | Hash-deduped record of ingested PDFs / CSVs | For the planned PDF importer phase |

Full DDL: [`pt/db/schema_portfolio.sql`](../../pt/db/schema_portfolio.sql).
Re-running the file is safe — every statement uses `IF NOT EXISTS` /
`DO $$ ... EXCEPTION` blocks.

## DB helpers (`pt/db/`)

| Module | What it does |
|--|--|
| [`connection.py`](../../pt/db/connection.py) | `get_conn()` context manager, `is_available()` health probe |
| [`migrate.py`](../../pt/db/migrate.py) | `apply_schema()`, `list_tables()`, `candles_has_asset_type()` |
| [`portfolios.py`](../../pt/db/portfolios.py) | CRUD + `archive` (soft) + `delete_hard` (test cleanup only) |
| [`transactions.py`](../../pt/db/transactions.py) | `insert`, `list_for_portfolio`, `soft_delete`, `audit_history`. `with_changed_by()` context manager sets the GUC the trigger reads |
| [`holdings.py`](../../pt/db/holdings.py) | `list_for_portfolio` (qty + total_cost + avg_cost from tx aggregate) and `list_for_portfolio_with_prices` (same plus `current_price`, `market_value`, `unrealized_pnl`) |
| [`assets.py`](../../pt/db/assets.py) | upsert / get / list / `find_similar` for asset master |
| [`prices.py`](../../pt/db/prices.py) | `latest_close(symbol, asset_type)` and `latest_close_many(keys)` against `public.candles` |
| [`news.py`](../../pt/db/news.py) | `upsert_many`, `list_for_symbol`, `latest_fetched_at`, `avg_sentiment` |
| [`insights.py`](../../pt/db/insights.py) | `insert` (with TTL), `latest_valid`, `list_for_symbol`, `delete` |

## The audit trigger

```sql
CREATE FUNCTION portfolio.fn_log_transaction_audit() RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO portfolio.transaction_audit (transaction_id, operation, new_data, changed_by)
    VALUES (NEW.id, 'INSERT', to_jsonb(NEW), current_setting('portfolio.changed_by', true));
    RETURN NEW;
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO portfolio.transaction_audit (...)
    VALUES (NEW.id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW), ...);
    RETURN NEW;
  END IF;
  ...
END;
$$ LANGUAGE plpgsql;
```

Reads the `portfolio.changed_by` GUC — set it via:

```python
with conn.cursor() as cur:
    cur.execute("SELECT set_config('portfolio.changed_by', %s, true)", (actor,))
```

The Python helpers in `transactions.py` accept a `changed_by` argument and
set the GUC inside the same transaction so the trigger picks it up.

## Gotchas

- **DELETE is intentionally not audited.** The trigger only fires on INSERT/
  UPDATE because hard-DELETE would create an audit row with an FK to a
  vanishing transaction. Production code uses soft-delete (`UPDATE deleted_at`),
  hard-delete is test-cleanup only. → fix: never add `DELETE` to the trigger
  `WHEN` clause; if real production hard-delete is ever needed, drop the
  audit FK or add `ON DELETE CASCADE` first.
- **`search_path = portfolio, public`.** Set in every `get_conn()` call.
  Bare `candles` resolves to `public.candles`, bare `transactions` to
  `portfolio.transactions`. Don't rely on this in DDL — always qualify
  schemas in the `.sql` file.
- **NUMERIC vs Decimal.** psycopg 3 maps NUMERIC ↔ `Decimal` correctly. If
  you use raw SQL via `cur.execute()` to compute money in the DB, the
  result still comes back as Decimal — don't `float()` it before
  comparing in tests.
- **`HAVING SUM(...) > 0` filters closed positions.** `holdings.list_for_portfolio`
  excludes positions with zero quantity by default. Pass `include_zero=True`
  to see fully exited positions.
- **`source_doc_id` UNIQUE is partial.** Idempotency on transactions is
  enforced via a UNIQUE INDEX `WHERE source_doc_id IS NOT NULL AND
  deleted_at IS NULL` — manual transactions (no source_doc_id) deliberately
  bypass it so users can record duplicate-looking trades intentionally.
- **Test cleanup deletes audit rows first.** `portfolios.delete_hard` walks
  audit → transactions → snapshots → portfolios in that order. If you add
  a new child table referencing transactions, extend `delete_hard` so
  isolated_portfolio fixture teardown doesn't FK-fail.

## Schema migration in CI

`.github/workflows/test.yml` bootstraps a minimal `public.candles` +
`public.market_meta` (claude-trader's tables) and then applies our
`schema_portfolio.sql`. Keep that bootstrap in sync if claude-trader's
schema changes the columns we depend on.
