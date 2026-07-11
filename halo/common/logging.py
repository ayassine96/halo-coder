#!/usr/bin/env python3
"""Structured JSON Lines logging for HALO Factory (REL-3)."""

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JsonLineFormatter(logging.Formatter):
    """Emit one JSON object per log line with SRS-required fields."""

    def format(self, record):
        obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", "unknown"),
            "spec_id": getattr(record, "spec_id", None),
            "event": getattr(record, "event", None),
            "message": record.getMessage(),
        }
        return json.dumps(obj, default=str)


def setup_logger(component: str, log_file: str = None):
    logger = logging.getLogger(component)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JsonLineFormatter())
        logger.addHandler(file_handler)

    def _log(level, msg, *, spec_id=None, event=None, **kwargs):
        extra = {"component": component}
        if spec_id:
            extra["spec_id"] = spec_id
        if event:
            extra["event"] = event
        logger.log(level, msg, extra=extra)

    return logger, _log


def log_event(logger, level, message, *, component="unknown", spec_id=None, event=None):
    """Convenience function matching SRS REL-3 structured log format."""
    record = logging.LogRecord(
        name=component, level=level, pathname="", lineno=0,
        msg=message, args=None, exc_info=None
    )
    record.component = component
    record.spec_id = spec_id
    record.event = event
    print(JsonLineFormatter().format(record))