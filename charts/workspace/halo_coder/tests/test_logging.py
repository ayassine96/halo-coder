"""Tests for the halo_coder.logging module."""

from __future__ import annotations

import io
import json
import unittest

from halo_coder.logging import StructuredLogger, get_logger
from halo_coder.protocols import Logger


class TestStructuredLogger(unittest.TestCase):
    def setUp(self) -> None:
        self.sink = io.StringIO()
        self.log = StructuredLogger("test.module", sink=self.sink)

    def _last_record(self) -> dict[str, object]:
        self.sink.seek(0)
        lines = [ln for ln in self.sink.read().split("\n") if ln.strip()]
        return json.loads(lines[-1])

    def test_isinstance_logger(self) -> None:
        self.assertIsInstance(self.log, Logger)

    def test_info_writes_json_line(self) -> None:
        self.log.info("hello")
        record = self._last_record()
        self.assertEqual(record["name"], "test.module")
        self.assertEqual(record["level"], "INFO")
        self.assertEqual(record["msg"], "hello")

    def test_debug_writes_debug_level(self) -> None:
        self.log.debug("trace")
        record = self._last_record()
        self.assertEqual(record["level"], "DEBUG")

    def test_warning_writes_warning_level(self) -> None:
        self.log.warning("caution")
        record = self._last_record()
        self.assertEqual(record["level"], "WARNING")

    def test_error_writes_error_level(self) -> None:
        self.log.error("fail")
        record = self._last_record()
        self.assertEqual(record["level"], "ERROR")

    def test_exception_includes_traceback(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            self.log.exception("caught")

        record = self._last_record()
        self.assertEqual(record["level"], "ERROR")
        self.assertIn("traceback", record["ctx"])  # type: ignore[operator]
        self.assertIn("ValueError: boom", record["ctx"]["traceback"])  # type: ignore[index]

    def test_keyword_context_appears_in_ctx(self) -> None:
        self.log.info("event", user="alice", count=5)
        record = self._last_record()
        self.assertEqual(record["ctx"]["user"], "alice")  # type: ignore[index]
        self.assertEqual(record["ctx"]["count"], 5)  # type: ignore[index]

    def test_timestamp_is_float(self) -> None:
        self.log.info("ts")
        record = self._last_record()
        self.assertIsInstance(record["ts"], float)
        self.assertGreater(record["ts"], 0)

    def test_no_ctx_when_no_kwargs(self) -> None:
        self.log.info("plain")
        record = self._last_record()
        self.assertNotIn("ctx", record)

    def test_multiple_records(self) -> None:
        self.log.info("first")
        self.log.info("second")
        self.sink.seek(0)
        lines = [ln for ln in self.sink.read().split("\n") if ln.strip()]
        self.assertEqual(len(lines), 2)

    def test_sink_is_redirectable(self) -> None:
        alt_sink = io.StringIO()
        log2 = StructuredLogger("alt", sink=alt_sink)
        log2.info("redirected")
        alt_sink.seek(0)
        content = alt_sink.read()
        self.assertIn("redirected", content)


class TestGetLogger(unittest.TestCase):
    def test_returns_logger(self) -> None:
        log = get_logger("my.module")
        self.assertIsInstance(log, Logger)
        self.assertIsInstance(log, StructuredLogger)

    def test_has_expected_name(self) -> None:
        sink = io.StringIO()
        log = get_logger("custom", sink=sink)
        log.info("x")
        sink.seek(0)
        record = json.loads(sink.read().split("\n")[0])
        self.assertEqual(record["name"], "custom")
