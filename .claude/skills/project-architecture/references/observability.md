# Observability — logging, request-ids, health probe

Stdlib-only logging (no extra deps). Request-id correlation across the
stack via `contextvar`. Enriched health probe so deploy smoke checks can
hit `/api/health` and immediately see DB latency + per-table counts.

## Logging configuration ([`pt/logging.py`](../../pt/logging.py))

`configure(level=PT_LOG_LEVEL, fmt=PT_LOG_FORMAT)` is **idempotent** —
safe to call from CLI entrypoints, FastAPI startup, tests. It clears any
existing root handlers (so uvicorn `--reload` doesn't double-log) and
installs a fresh one with either `HumanFormatter` or `JsonFormatter`.

| Env var | Default | Effect |
|--|--|--|
| `PT_LOG_FORMAT` | `human` | `human` (TTY-coloured if stderr is a tty) or `json` (one JSON object per line) |
| `PT_LOG_LEVEL` | `INFO` | Standard stdlib level names |

JSON format is the prod default (set in `Dockerfile` and
`docker-compose.prod.yml`). Human is the dev default — handy under uvicorn
`--reload`.

### JSON output shape

```json
{"ts":"2026-04-26T20:04:25.123Z", "level":"INFO", "logger":"pt.api",
 "msg":"request", "request_id":"a1b2c3d4e5f6...",
 "method":"GET", "path":"/api/holdings", "status":200, "latency_ms":15}
```

Caller-supplied `extra={...}` fields are flattened directly onto the
top-level object. Stdlib's reserved record attributes are filtered out so
they don't double-write.

## Request-id middleware ([`pt/api/middleware.py`](../../pt/api/middleware.py))

`RequestLogMiddleware` runs on every request:

1. Reads `X-Request-ID` from the request header. If missing, generates a
   fresh `uuid.uuid4().hex[:16]`.
2. Stashes the id in a `contextvars.ContextVar`.
3. Calls the wrapped handler.
4. Logs `extra={method, path, status, latency_ms}` on completion.
5. Echoes `X-Request-ID` in the response header.

`RequestIdLogFilter` is installed once on the root logger via
`install_logging_filter()`. On every record it checks the contextvar and
sets `record.request_id` if a request is active. This means **any library
that logs** (psycopg, httpx, uvicorn, your own modules) gets the id
without doing anything.

`HumanFormatter` renders the id as `[a1b2c3d4]` between logger and msg.
`JsonFormatter` includes it as a top-level field.

`/api/health` 2xx is **not** logged (suppressed in the middleware) — only
failures show up. Avoids cron-noise in prod logs.

## Health probe ([`pt/api/app.py`](../../pt/api/app.py))

`GET /api/health` returns:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "now": "2026-04-26T20:04:25+00:00",
  "db": {"status": "ok", "latency_ms": 12},
  "counts": {
    "portfolios": 1, "transactions": 6, "candles": 84,
    "news": 0, "insights": 0
  }
}
```

`status` flips to `"degraded"` if the DB ping fails or any subsequent
count query throws — useful for deploys (the smoke check shows whether
the new schema landed).

## Tracing a request end-to-end

```
client                            api                              psycopg
  │  GET /api/holdings              │                                 │
  ├─────────────────────────────────►│                                 │
  │                                  │  uuid → contextvar              │
  │                                  │  log "request"                  │
  │                                  │  extra={request_id, method, ...}│
  │                                  │                                 │
  │                                  │  query holdings ───────────────►│
  │                                  │  log "DB query 1.4ms"           │
  │                                  │  ◄──────────────────────────────│
  │  ◄────────────── X-Request-ID ───┤                                 │
```

Filter logs by `request_id=a1b2c3d4` (e.g. `jq` on JSON or `grep` on
human format) to get the full slice.

## Gotchas

- **Don't bypass `configure()`.** Test suites that call
  `logging.basicConfig()` themselves break the format consistency. If a
  test needs to assert on a log line, capture via pytest's `caplog`
  fixture — the formatter doesn't matter for assertions.
- **`uvicorn.access` is silenced.** We disable propagation in
  `configure()` so we don't double-log every request (uvicorn's own access
  log + ours). If you want uvicorn's verbose access logs back, either
  remove that line or set `uvicorn`'s `--access-log`.
- **`PT_LOG_FORMAT=json` in dev makes uvicorn `--reload` ugly.** Each
  reload recompiles → fresh `configure()` → fresh handlers, but anything
  the reloader itself prints (file-watch events) still goes through
  uvicorn's own logger. Use `PT_LOG_FORMAT=human` for dev.
- **`X-Request-ID` is *not* validated.** Clients can pass anything. We
  trust it because logs are an internal observability surface. If you
  ever expose this externally as a security boundary, sanitise (strip
  newlines, length-limit) before logging.
- **`contextvars` cross task boundaries within asyncio**, but a regular
  `threading.Thread` started inside a request handler does NOT inherit
  the context. If you ever spawn a worker thread, copy the id manually:
  `rid = _request_id.get()` then `extra={"request_id": rid}` in the thread.
- **The `log.exception()` path in middleware** re-raises after logging.
  Don't swallow exceptions in the middleware — let FastAPI's error
  handler return the 500 so the response body matches the framework's
  conventions.
