"""Structured logging infrastructure.

Provides a protocol-compliant :class:`StructuredLogger` that routes
messages to stderr with consistent formatting. Library code must never
use ``print()`` directly — inject a :class:`Logger` instead.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any, TextIO

from halo_coder.protocols import Logger


class StructuredLogger(Logger):
    """Thread-safe structured logger writing to stderr.

    Each log line is a JSON object with timestamp, level, message, and
    optional keyword context. The logger name is automatically derived
    from the calling module.

    Usage::

        log = StructuredLogger("halo_coder.config")
        log.info("configuration loaded", readonly=True, auth="basic")
    """

    def __init__(
        self,
        name: str,
        *,
        sink: TextIO | None = None,
    ) -> None:
        """Initialize a logger.

        Args:
            name: The logger name (typically ``__name__`` of the calling module).
            sink: Output stream (defaults to ``sys.stderr``).
        """
        self._name = name
        self._sink = sink or sys.stderr
        self._lock = threading.Lock()

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log("DEBUG", msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log("INFO", msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log("WARNING", msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log("ERROR", msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        import traceback

        kwargs["traceback"] = traceback.format_exc().strip()
        self._log("ERROR", msg, **kwargs)

    def _log(self, level: str, msg: str, **kwargs: Any) -> None:
        record: dict[str, object] = {
            "ts": time.time(),
            "name": self._name,
            "level": level,
            "msg": msg,
        }
        if kwargs:
            record["ctx"] = kwargs
        line = json.dumps(record, default=str)
        with self._lock:
            self._sink.write(line + "\n")
            self._sink.flush()


def get_logger(name: str, *, sink: TextIO | None = None) -> Logger:
    """Factory for the default structured logger.

    Args:
        name: The logger name (pass ``__name__`` from the calling module).
        sink: Optional output stream.

    Returns:
        A :class:`Logger` instance.
    """
    return StructuredLogger(name, sink=sink)


__all__ = ["StructuredLogger", "get_logger"]
