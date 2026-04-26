# Deployment — Docker, nginx, CI

The portfolio ships as a three-container stack with its own TimescaleDB and
a persistent named volume. nginx fronts the React SPA and proxies `/api` to
the FastAPI container; the API is internal-only by default.

## Containers

| Container | Image | Built from | Exposed | State on `down` |
|--|--|--|--|--|
| `pt-timescaledb` | `timescale/timescaledb:latest-pg16` | (upstream) | internal `5432` | volume `pt_db_data` survives |
| `pt-api` | `portfolio-api:latest` | [`Dockerfile`](../../Dockerfile) | internal `8430` | stateless |
| `pt-frontend` | `portfolio-frontend:latest` | [`frontend/Dockerfile`](../../frontend/Dockerfile) | host `:5174 → 80` | stateless |
| `pt-cron` | `portfolio-api:latest` (re-used) | — | none (sidecar) | stateless — fires `pt sync daily` once per day at `PT_CRON_HOUR_UTC` (default 06 UTC) |

Bring up: `docker compose -f docker-compose.prod.yml up -d --build`
Reset everything (drops the volume!): `docker compose -f docker-compose.prod.yml down -v`

## Compose file

[`docker-compose.prod.yml`](../../docker-compose.prod.yml) keeps the api container
internal — only the frontend port is published. nginx inside `pt-frontend` resolves
`pt-api:8430` via the default compose network. The DB hostname `pt-timescaledb`
is set as `PT_DB_HOST` in the api container env. Healthchecks gate startup
ordering: `pt-frontend` waits for `pt-api` to be healthy, which in turn waits
for `pt-timescaledb`.

## DB schema bootstrap

On the **first** TimescaleDB start (volume empty), the image's
`/docker-entrypoint-initdb.d/` hook runs SQL files in alphabetical order:

| Mounted path | Source |
|--|--|
| `01_public_schema.sql` | [`db/init/01_public_schema.sql`](../../db/init/01_public_schema.sql) — minimal `public.candles` + `public.market_meta` (mirrors what claude-trader writes) |
| `02_portfolio_schema.sql` | [`pt/db/schema_portfolio.sql`](../../pt/db/schema_portfolio.sql) — bind-mounted from the source tree, runs the same idempotent DDL the dev `pt db migrate` uses |

`db/init/01_public_schema.sql` is intentionally minimal — only the columns the
portfolio writes/reads (`asset_type`, `exchange` etc. are added by
`schema_portfolio.sql`'s ALTERs). Keep it in sync if claude-trader's schema
changes the columns we depend on.

## API container

[`Dockerfile`](../../Dockerfile) is single-stage Python 3.12-slim:

- non-root user `ptuser` (uid 10001), `WORKDIR=/app`
- two-step pip install (deps first, code second) so layer caching works
  when only source changes
- `PT_LOG_FORMAT=json` baked in so prod logs are JSON by default
- HEALTHCHECK pings `/api/health` every 30s (5s start period)
- entrypoint `uvicorn pt.api.app:app --host 0.0.0.0 --port 8430`

## Frontend container

[`frontend/Dockerfile`](../../frontend/Dockerfile) is multi-stage:

1. **build**: `node:20-alpine`, `npm ci`, `tsc -b && vite build`
2. **runtime**: `nginx:1.27-alpine` serving `/app/dist` from the build stage

[`frontend/nginx.conf`](../../frontend/nginx.conf):

- `/assets/*` → 1y cache, `Cache-Control: immutable` (Vite emits hashed names)
- `/api/*` → `proxy_pass http://pt-api:8430` with `X-Real-IP`,
  `X-Forwarded-For`, `X-Forwarded-Proto` set
- catch-all `try_files $uri $uri/ /index.html` for SPA routing
- `access_log off` on `/api/health` to keep logs tidy

## Daily cron sidecar (`pt-cron`)

[`docker-compose.prod.yml:cron`](../../docker-compose.prod.yml) runs once a
day to keep market data fresh without manual `pt sync ...` invocations.

- **Image**: re-uses `portfolio-api:latest` so there's no second build to
  maintain; the `pt` CLI is on `$PATH` via the project's
  `[project.scripts]` entry point.
- **Schedule**: pure shell loop, sleeps until next `PT_CRON_HOUR_UTC:00`
  (default `06`). One run per 24h. Override via `.env`:
  `PT_CRON_HOUR_UTC=4` → 04:00 UTC.
- **What it runs**: `pt sync daily` →
  [`pt/jobs/daily.py:run`](../../pt/jobs/daily.py).
  - `_step_fx`: Frankfurter latest rates (EUR base).
  - `_step_auto_prices`: per active portfolio, calls
    [`pt.api.routes.sync.sync_portfolio_prices`](../../pt/api/routes/sync.py)
    with `days=5` (cheap, idempotent — TimescaleDB primary key swallows
    duplicates).
  - `_step_benchmarks`: every entry of `pt.jobs.benchmarks.BENCHMARKS`
    gets `ensure_history(days=5)`.
  - `_step_snapshots`: today's `write_today` for every active portfolio.
- **Failure handling**: each step is wrapped in try/except. One failing
  step doesn't abort the others; the orchestrator returns
  `ok: False` + per-step error and exits non-zero. `docker logs pt-cron`
  surfaces the JSON line for debugging.
- **First-time setup on a fresh prod DB**: after `docker compose up`,
  run `docker exec pt-api pt db migrate` to apply any post-bootstrap
  schema additions (the volume's first-start init only ships the
  `02_portfolio_schema.sql` snapshot from compose-up time — later schema
  changes need an explicit migrate). Smoke-test the orchestration via
  `docker exec pt-cron pt sync daily` (forces an immediate run instead
  of waiting until 06:00 UTC).
- **Manual trigger** (any time): `docker exec pt-cron pt sync daily`.
- **Disable**: `docker compose -f docker-compose.prod.yml stop cron`.

## CI

[`.github/workflows/test.yml`](../../.github/workflows/test.yml):

- **backend job**: TimescaleDB service container on the runner (port 5434),
  bootstrap script (`CREATE EXTENSION timescaledb` + minimal candles +
  market_meta + `pt/db/schema_portfolio.sql`), `pytest -v`. Tests that
  require the LGT reference PDF skip gracefully — the file is gitignored.
- **frontend job**: `npm ci`, `tsc -b`, `npm run build`. No frontend tests
  are wired in yet (vitest isn't running in CI), but the type-checker +
  build catch most drift.

Triggered on `push`/`pull_request` to `main` plus manual `workflow_dispatch`.

## Env vars (production)

| Var | Default | Effect |
|--|--|--|
| `PT_DB_HOST` | `pt-timescaledb` | hostname of the DB container |
| `PT_DB_NAME` | `claude_trader` | DB name. We share the name with claude-trader so a single DB can serve both repos when colocated. |
| `PT_DB_USER` | `trader` | DB user |
| `PT_DB_PASSWORD` | `trader_dev_2024` | **change in real prod**. Compose passes through; nothing baked into images. |
| `PT_DB_SCHEMA` | `portfolio` | search_path schema |
| `PT_LOG_FORMAT` | `json` | set `human` for dev runs |
| `PT_LOG_LEVEL` | `INFO` | stdlib level names |
| `OPENROUTER_API_KEY` | (empty) | passed through; consumed by `pt/insights/llm.py` (currently dormant) |
| `TWELVE_DATA_API_KEY` | (empty) | stocks/ETFs sync |
| `FINNHUB_API_KEY` | (empty) | per-stock news + earnings |
| `MARKETAUX_API_KEY` | (empty) | multi-asset news |

Missing API keys cause graceful degradation — the route returns
`{ok: false, error: "...API_KEY env var not set"}` rather than crashing.

## Sharing the DB with claude-trader

Two options when both repos run on the same host:

1. **Default**: each gets its own TimescaleDB container (`ct-timescaledb`,
   `pt-timescaledb`), separate volumes. Schemas overlap on `public.candles`
   only by name; the two `candles` tables are physically distinct.
2. **Shared**: point both repos at one DB. Set `PT_DB_HOST=ct-timescaledb`
   and join the claude-trader compose network (`networks: external: true`).
   Drop the `timescaledb` service from `docker-compose.prod.yml`. The
   `pt/db/schema_portfolio.sql` ALTERs on `public.candles` are
   forwards-compatible with claude-trader's schema, so this is safe.

Stefan currently runs option 1 in dev (separate DBs). Option 2 is the
right choice when claude-trader's BTC dataset becomes valuable input for
portfolio analytics.

## Gotchas

- **First-start init only.** `/docker-entrypoint-initdb.d/` files run **once**,
  when the volume is empty. After that they're never re-executed. To re-bootstrap,
  `docker compose down -v` (loses all data!) and bring up again. For schema
  changes on a populated DB, run `pt db migrate` from the dev shell — the
  SQL is idempotent so it works on a live DB too.
- **The api container is not exposed to the host.** Only `:5174` is published.
  Want to hit `/api/*` directly from your host shell? Either go through
  nginx (`http://localhost:5174/api/health`) or `docker compose exec api
  curl http://localhost:8430/api/health` from inside.
- **`schema_portfolio.sql` is bind-mounted into the DB container** as the
  init script. If you edit it, the change only takes effect on the NEXT
  fresh DB volume — for the current volume, also run `pt db migrate` (which
  applies the same file via psycopg).
- **Compose network is `claude-trader_default` by default in dev**, but the
  prod compose creates its own. Don't mix them — the api would fail to
  resolve `ct-timescaledb` from inside the wrong network.
- **Frontend build needs the API URL at build time? No.** All API calls go
  through `/api/*`, which nginx proxies. The image contains no API hostname.
  This means one image works in dev, prod, and behind any reverse proxy.
- **CORS is open** for `localhost:5173/5174/8430` (configured in
  `pt/api/app.py`). The frontend container goes through nginx-proxy, so
  CORS doesn't trip. If you ever expose the api directly to the public,
  tighten the `allow_origins` list first.
- **Volume name is hard-coded** as `pt_db_data` in the compose. If you run
  multiple instances on the same Docker host, override with
  `docker-compose -p <project>` so volumes don't collide.
- **Docker Compose v2 may NOT auto-load `.env` on macOS.** When
  `${VAR:-}` substitution lands in the merged compose config as an empty
  string even though `.env` defines the var, `.env` was never read for
  the substitution pass. Workaround: source the file into the shell
  before invoking compose so the vars enter as real shell env:
  ```bash
  set -a && . .env && set +a && \
    docker compose -f docker-compose.prod.yml up -d --force-recreate api
  ```
  Verify with `docker inspect pt-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep API_KEY`.
  Symptom: API container reports `*_API_KEY env var not set` despite a
  populated `.env` next to the compose file.
- **`yfinance` is in `pyproject.toml` dependencies** (not extras) because
  the auto-prices route imports it lazily for the SIX-listing fallback.
  Image rebuilds need `docker compose ... up -d --build api` to pick up
  pyproject changes — restart alone won't reinstall the package.
