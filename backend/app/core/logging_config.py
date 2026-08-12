"""Structured JSON logging with request/trace correlation. This is the
"basic" observability groundwork (PRD monitoring notes) laid down ahead of
the full Prometheus/Grafana/Jaeger stack, which is deferred until after
deployment. Every log record picks up whatever request_id/trace_id is
currently bound via `bind_context`, so API and worker logs for the same
logical operation can be grepped together (e.g. `jq 'select(.trace_id ==
"...")'`) even without a tracing backend in place yet.
"""

import contextvars
import json
import logging
import sys
from typing import Any

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")

# Every attribute a stock LogRecord carries — anything else on the record
# (from `extra=`) is application-supplied and gets included in the JSON line.
_STANDARD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message",
}


def bind_context(*, request_id: str | None = None, trace_id: str | None = None) -> None:
    if request_id is not None:
        _request_id.set(request_id)
    if trace_id is not None:
        _trace_id.set(trace_id)


def get_trace_id() -> str:
    return _trace_id.get()


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        record.trace_id = _trace_id.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "trace_id": getattr(record, "trace_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent so it's safe to call from both the API process and each
    Celery worker/beat process without ever accumulating duplicate handlers.
    """
    root = logging.getLogger()
    if any(getattr(h, "_scaffold_json", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_ContextFilter())
    handler._scaffold_json = True
    root.handlers = [handler]
    root.setLevel(level)
