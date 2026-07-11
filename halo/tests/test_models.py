#!/usr/bin/env python3
"""Unit tests for halo.common.models."""

import unittest
from halo.common.models import (
    Spec, AgentTask, EventMessage, TdadRequest, TdadResponse,
    SPEC_STATUS_DRAFT, SPEC_STATUS_READY, ALL_STATUSES,
    CHANNEL_LOGS, CHANNEL_APPROVALS, CHANNEL_ALERTS, CHANNEL_METRICS,
    STREAM_QUEUE,
)


class TestSpecModel(unittest.TestCase):

    def test_defaults(self):
        s = Spec(id="SPEC-001", title="Test", status="draft")
        self.assertEqual(s.depends_on, [])
        self.assertEqual(s.blocks, [])
        self.assertEqual(s.tags, [])
        self.assertEqual(s.author, "halo-agent")
        self.assertEqual(s.body, "")

    def test_to_dict(self):
        s = Spec(id="SPEC-001", title="Test", status="draft", tags=["api"])
        d = s.to_dict()
        self.assertEqual(d["id"], "SPEC-001")
        self.assertEqual(d["status"], "draft")
        self.assertEqual(d["tags"], ["api"])


class TestAgentTaskModel(unittest.TestCase):

    def test_stream_key(self):
        t = AgentTask(spec_id="SPEC-001", role="planner", model_profile="halo-reasoning")
        self.assertEqual(t.stream_key(), "halo:factory:queue:SPEC-001")


class TestEventMessage(unittest.TestCase):

    def test_auto_timestamp(self):
        e = EventMessage(channel=CHANNEL_LOGS, event_type="test")
        self.assertTrue(e.timestamp)
        self.assertEqual(e.channel, CHANNEL_LOGS)

    def test_constants(self):
        self.assertEqual(CHANNEL_LOGS, "halo:factory:logs")
        self.assertEqual(CHANNEL_APPROVALS, "halo:factory:approvals")
        self.assertEqual(CHANNEL_ALERTS, "halo:factory:alerts")
        self.assertEqual(CHANNEL_METRICS, "halo:factory:metrics")
        self.assertEqual(STREAM_QUEUE, "halo:factory:queue")


class TestStatusEnums(unittest.TestCase):

    def test_all_statuses(self):
        expected = {"draft", "ready", "in_progress", "implemented", "merged",
                    "failed_red", "failed_green", "failed_e2e"}
        self.assertEqual(set(ALL_STATUSES), expected)


if __name__ == '__main__':
    unittest.main()