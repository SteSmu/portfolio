# CLI (`pt`)

Typer entry [`pt/cli.py`](../../pt/cli.py), seven sub-apps that mirror the
REST routers one-for-one. Same data flows, same DB helpers, both surfaces
have feature parity except for things only meaningful in a shell (like
audit-trail tables).

## Commands

```text
pt --version
pt --help

pt db          migrate          apply schema_portfolio.sql (idempotent)
               status           tables + candles columns

pt portfolio   create NAME [-c EUR]
               list [--all] [--json]
               show ID
               archive ID

pt tx          add -p PID -s SYM -t TYPE -a ACTION -q QTY --price P -c CUR ...
               list -p PID [--symbol X --action a --limit N --include-deleted]
               show TX_ID
               audit TX_ID
               delete TX_ID --yes

pt holdings    list -p PID [--include-zero]
               show -p PID -s SYM -t TYPE

pt asset       add SYMBOL TYPE -n NAME -c CURRENCY [-e EXCHANGE --isin ...]
               list [--type T --search S]
               show SYMBOL TYPE
               find QUERY [--limit N]

pt sync        fx [-b EUR -q USD -q CHF --days N]
               crypto --coin bitcoin --vs-currency usd --days N
               stock SYMBOL [--interval 1day --outputsize N --asset-type stock]

pt perf        summary    -p PID [-m fifo|lifo|average]
               cost-basis -p PID [-m ...] [-s SYMBOL]
               realized   -p PID [-m ...] [--year YYYY]
```

## Conventions

Every data command supports `--json`. Output schema matches the REST
response shape — agent-friendly, parseable.

Exit codes:
- `0` ok
- `1` general error (DB unreachable, fetcher 5xx, etc.)
- `2` usage error (bad arg, validation rejection)
- `3` not found
- `5` conflict (duplicate portfolio name)

Destructive commands (`pt tx delete`) require `--yes` in non-interactive
shells, otherwise prompt. Never deletes anything silently.

## File layout

| Module | Sub-app |
|--|--|
| [`cli.py`](../../pt/cli.py) | Typer root, registers everything |
| [`cli_db.py`](../../pt/cli_db.py) | `pt db` |
| [`cli_portfolio.py`](../../pt/cli_portfolio.py) | `pt portfolio` |
| [`cli_tx.py`](../../pt/cli_tx.py) | `pt tx` |
| [`cli_holdings.py`](../../pt/cli_holdings.py) | `pt holdings` |
| [`cli_asset.py`](../../pt/cli_asset.py) | `pt asset` |
| [`cli_sync.py`](../../pt/cli_sync.py) | `pt sync` |
| [`cli_perf.py`](../../pt/cli_perf.py) | `pt perf` |

The entry point in [`pyproject.toml`](../../pyproject.toml) is
`pt = "pt.cli:app"` — installed with `pip install -e .`.

## Tests

- [`tests/test_smoke.py`](../../tests/test_smoke.py) — `--version`, `--help`,
  package import.
- [`tests/test_cli_smoke.py`](../../tests/test_cli_smoke.py) — every sub-app
  registered, `pt portfolio create` round-trip, conflict exit code.
- [`tests/test_cli_perf.py`](../../tests/test_cli_perf.py) — performance
  commands end-to-end with `isolated_portfolio` fixture.
- [`tests/test_cli_sync.py`](../../tests/test_cli_sync.py) — sync sub-app
  registration only (real HTTP not exercised here — fetchers themselves
  are unit-tested).

## Gotchas

- **`pt tx add` parses `--qty` and `--price` via `Decimal(replace(",", "."))`.**
  Both `1.23` and `1,23` work. But `1_000.50` also works (underscores
  stripped), which can confuse copy-paste from spreadsheets — usually fine,
  but flag if it ever bites a user.
- **`--executed-at` defaults to "now (UTC)".** Pass an ISO date or datetime
  explicitly when backfilling old trades. Naive datetimes get assumed UTC.
- **Rich tables truncate without warning.** `pt tx list` columns like
  "When" or "Symbol" can show `2026-0…` if your terminal is narrow.
  `--json` is the source of truth for scripting; the rich table is for
  glance-only.
- **Sub-apps register in `cli.py`.** Adding a new sub-app means a new
  `cli_<name>.py` file with `app = typer.Typer(...)` plus an
  `app.add_typer(...)` line in `cli.py`. Keep the docstring of every
  sub-app's `app` declaration short — Typer renders it as the top-line
  help in `pt --help`.
- **`pt db migrate` is idempotent.** Re-runnable after every schema change.
  Don't ship "schema versions" or alembic migrations for now — the SQL
  file uses `IF NOT EXISTS` / `DO $$` blocks throughout and is small
  enough that diffing it directly is fine.
- **`--json` errors go to stderr, not stdout.** `cli_portfolio.cmd_create`
  and similar print error-shaped JSON to stderr on failure (semantic exit
  code), keeping stdout clean for piping. Callers that swallow stderr
  miss the diagnosis.
