#!/usr/bin/env python3
"""Unit tests for halo.common.logging."""

import json
import logging
import unittest
from halo.common.logging import JsonLineFormatter, setup_logger, log_event


class TestJsonLineFormatter(unittest.TestCase):

    def test_format(self):
        formatter = JsonLineFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=None, exc_info=None
        )
        record.component = "supervisor"
        record.spec_id = "SPEC-001"
        record.event = "start"
        line = formatter.format(record)
        obj = json.loads(line)
        self.assertEqual(obj["level"], "INFO")
        self.assertEqual(obj["message"], "test message")
        self.assertEqual(obj["component"], "supervisor")
        self.assertEqual(obj["spec_id"], "SPEC-001")
        self.assertEqual(obj["event"], "start")
        self.assertIn("timestamp", obj)

    def test_format_defaults(self):
        formatter = JsonLineFormatter()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="fail", args=None, exc_info=None
        )
        line = formatter.format(record)
        obj = json.loads(line)
        self.assertEqual(obj["component"], "unknown")
        self.assertIsNone(obj["spec_id"])
        self.assertIsNone(obj["event"])


class TestSetupLogger(unittest.TestCase):

    def test_returns_logger(self):
        logger, log_fn = setup_logger("test")
        self.assertEqual(logger.name, "test")

    def test_log_event(self):
        log_event(None, logging.INFO, "msg", component="test", spec_id="SPEC-001", event="created")


if __name__ == '__main__':
    unittest.main()