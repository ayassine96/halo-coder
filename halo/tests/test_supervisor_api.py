#!/usr/bin/env python3
"""Unit tests for Supervisor HTTP API (A9, FF-R3, FF-R4)."""

import os
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi.testclient import TestClient

from halo.factory.supervisor_api import app, _csrf_tokens
from halo.factory.supervisor import Supervisor


class TestSupervisorAPIBase(unittest.TestCase):

    def setUp(self):
        _csrf_tokens.clear()
        self.sup = Supervisor()
        app.state.supervisor = self.sup
        self.client = TestClient(app)

    def tearDown(self):
        _csrf_tokens.clear()


class TestHealthEndpoint(TestSupervisorAPIBase):

    def test_health_no_supervisor(self):
        del app.state.supervisor
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

    def test_health_with_supervisor(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("paused", data)
        self.assertIn("redis_connected", data)
        self.assertIn("k3s_connected", data)


class TestCSRFToken(TestSupervisorAPIBase):

    def test_get_csrf_token(self):
        resp = self.client.get("/api/csrf-token")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("csrf_token", resp.json())

    def test_csrf_token_is_unique(self):
        t1 = self.client.get("/api/csrf-token").json()["csrf_token"]
        t2 = self.client.get("/api/csrf-token").json()["csrf_token"]
        self.assertNotEqual(t1, t2)


class TestStateEndpoint(TestSupervisorAPIBase):

    def test_state_returns_structure(self):
        resp = self.client.get("/api/state")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("specs", data)
        self.assertIn("devpods", data)
        self.assertIn("model_metrics", data)
        self.assertIn("logs", data)
        self.assertIn("paused", data)

    def test_state_paused_reflects_supervisor(self):
        self.sup._paused = True
        resp = self.client.get("/api/state")
        self.assertEqual(resp.json()["paused"], True)


class TestSpecsEndpoint(TestSupervisorAPIBase):

    def test_list_specs_empty(self):
        resp = self.client.get("/api/specs")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["specs"], [])

    def test_get_spec_not_found(self):
        resp = self.client.get("/api/spec/SPEC-999")
        self.assertEqual(resp.status_code, 404)


class TestMutations(TestSupervisorAPIBase):

    def test_approve_without_csrf_rejected(self):
        resp = self.client.post("/api/approve", json={"spec_id": "SPEC-001"})
        self.assertEqual(resp.status_code, 403)

    def test_approve_with_valid_csrf(self):
        token = self.client.get("/api/csrf-token").json()["csrf_token"]
        resp = self.client.post("/api/approve", json={
            "spec_id": "SPEC-001", "csrf_token": token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "approved")

    def test_reject_with_valid_csrf(self):
        token = self.client.get("/api/csrf-token").json()["csrf_token"]
        resp = self.client.post("/api/reject", json={
            "spec_id": "SPEC-001", "reason": "bad", "csrf_token": token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "rejected")

    def test_trigger_with_valid_csrf(self):
        from halo.common.models import Spec
        mock_spec = Spec(id="SPEC-001", title="Test", status="draft",
                         file_path="/tmp/nonexistent.md")
        token = self.client.get("/api/csrf-token").json()["csrf_token"]
        with patch.object(self.sup, "scan_projects", return_value={"SPEC-001": mock_spec}):
            resp = self.client.post("/api/trigger", json={
                "spec_id": "SPEC-001", "csrf_token": token
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "triggered")

    def test_kill_with_valid_csrf(self):
        token = self.client.get("/api/csrf-token").json()["csrf_token"]
        resp = self.client.post("/api/kill", json={
            "spec_id": "SPEC-001", "csrf_token": token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "killed")

    def test_pause_with_valid_csrf(self):
        token = self.client.get("/api/csrf-token").json()["csrf_token"]
        resp = self.client.post("/api/pause", json={"csrf_token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "paused")

    def test_pause_toggle_resume(self):
        token1 = self.client.get("/api/csrf-token").json()["csrf_token"]
        resp1 = self.client.post("/api/pause", json={"csrf_token": token1})
        self.assertEqual(resp1.json()["status"], "paused")
        self.assertTrue(self.sup._paused)

        token2 = self.client.get("/api/csrf-token").json()["csrf_token"]
        resp2 = self.client.post("/api/pause", json={"csrf_token": token2})
        self.assertEqual(resp2.json()["status"], "resumed")
        self.assertFalse(self.sup._paused)

    def test_csrf_token_consumed(self):
        token = self.client.get("/api/csrf-token").json()["csrf_token"]
        self.client.post("/api/approve", json={"spec_id": "S1", "csrf_token": token})
        resp2 = self.client.post("/api/approve", json={"spec_id": "S2", "csrf_token": token})
        self.assertEqual(resp2.status_code, 403)


class TestSupervisorMetrics(TestSupervisorAPIBase):

    def test_metrics(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("halo_supervisor_up", resp.text)


if __name__ == "__main__":
    unittest.main()