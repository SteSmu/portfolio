"""FastAPI middleware: per-request id + structured access log.

Adds an `X-Request-ID` header to every response (echoes the client's value if
present, otherwise generates a UUID v4 hex). The id is propagated to every log
record emitted during the request so a single request can be traced end-to-end.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pt.logging import get_logger

_request_id: ContextVar[str | None] = ContextVar("pt_request_id", default=None)


class RequestIdLogFilter(logging.Filter):
    """Attach the active request id to every emitted record. Installed on root."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = _request_id.get()
        if rid is not None:
            record.request_id = rid
        return True


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Log start + completion of every request with method/path/status/latency."""

    def __init__(self, app, *, logger_name: str = "pt.api"):
        super().__init__(app)
        self._log = get_logger(logger_name)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = _request_id.set(rid)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            latency_ms = int((time.monotonic() - start) * 1000)
            self._log.exception(
                "request failed",
                extra={"method": request.method, "path": request.url.path,
                       "latency_ms": latency_ms},
            )
            raise
        finally:
            _request_id.reset(token)

        latency_ms = int((time.monotonic() - start) * 1000)
        # Suppress chatty health-check logs unless they fail
        if not (request.url.path == "/api/health" and response.status_code < 400):
            self._log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                },
            )
        response.headers["X-Request-ID"] = rid
        return response


def install_logging_filter() -> None:
    """Attach the request-id filter to the root logger so all libs benefit."""
    root = logging.getLogger()
    if not any(isinstance(f, RequestIdLogFilter) for f in root.filters):
        root.addFilter(RequestIdLogFilter())
