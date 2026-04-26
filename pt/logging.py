"""Logging configuration — single entry point used by both the API and the CLI.

We use stdlib logging only (no extra deps). Two formats:
  - human:  short timestamp + level + logger + message, color-friendly
  - json:   one JSON object per line, easy to ship to Loki / Datadog / CloudWatch

Pick via env: PT_LOG_FORMAT=human|json (default human in dev, json under Docker).
PT_LOG_LEVEL controls verbosity (default INFO).

The FastAPI middleware in `pt.api.middleware` adds a per-request `request_id`
to every log record via `extra={...}` so a single request can be traced through
the stack.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

DEFAULT_LEVEL = os.getenv("PT_LOG_LEVEL", "INFO").upper()
DEFAULT_FORMAT = os.getenv("PT_LOG_FORMAT", "human").lower()

# Reserved attributes on stdlib LogRecord — we mustn't shadow them when emitting JSON.
_LOGRECORD_DEFAULTS = set(logging.LogRecord(
    "x", logging.INFO, "x", 0, "x", None, None,
).__dict__.keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Serialise records as a single JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Surface caller-supplied `extra=` fields (request_id, latency_ms, ...).
        for key, value in record.__dict__.items():
            if key not in _LOGRECORD_DEFAULTS:
                payload[key] = value
        return json.dumps(payload, default=str, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """Compact human-readable format — colour codes when stderr is a TTY."""

    _LEVEL_COLOURS = {
        "DEBUG": "\x1b[37m",     # gray
        "INFO":  "\x1b[36m",     # cyan
        "WARNING": "\x1b[33m",   # yellow
        "ERROR": "\x1b[31m",     # red
        "CRITICAL": "\x1b[1;31m",
    }
    _RESET = "\x1b[0m"

    def __init__(self, *, use_colours: bool):
        super().__init__()
        self.use_colours = use_colours

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        level = record.levelname
        colour = self._LEVEL_COLOURS.get(level, "") if self.use_colours else ""
        reset = self._RESET if self.use_colours else ""
        rid = getattr(record, "request_id", None)
        rid_part = f" [{rid}]" if rid else ""
        msg = record.getMessage()
        line = f"{ts} {colour}{level:<7}{reset} {record.name}{rid_part} {msg}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure(
    *,
    level: str = DEFAULT_LEVEL,
    fmt: str = DEFAULT_FORMAT,
    stream=None,
) -> None:
    """Idempotent — safe to call from CLI entrypoints, FastAPI startup, tests."""
    stream = stream or sys.stderr
    root = logging.getLogger()
    root.setLevel(level)
    # Clear any pre-existing handlers so we don't double-log under uvicorn reload.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(stream)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(HumanFormatter(use_colours=stream.isatty()))
    root.addHandler(handler)

    # Tame uvicorn — its access logs duplicate ours via the request middleware.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
