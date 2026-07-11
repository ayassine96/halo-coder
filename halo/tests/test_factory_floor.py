#!/usr/bin/env python3
"""Unit tests for Factory Floor dashboard (Stage 8 — FF-R1..FF-R7, SEC-6)."""

import unittest

from fastapi.testclient import TestClient
from halo.factory_floor.app import app


class TestFactoryFloorEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_metrics(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("halo_factory_floor_up", resp.text)

    def test_state_snapshot(self):
        resp = self.client.get("/api/state")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("specs", data)
        self.assertIn("devpods", data)
        self.assertIn("model_metrics", data)

    def test_list_specs(self):
        resp = self.client.get("/api/specs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("specs", resp.json())


class TestCSRFProtection(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_get_csrf_token(self):
        resp = self.client.get("/api/csrf-token")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("csrf_token", resp.json())

    def test_approve_without_csrf_rejected(self):
        resp = self.client.post("/api/approve", json={"spec_id": "SPEC-001"})
        self.assertEqual(resp.status_code, 403)

    def test_approve_with_valid_csrf(self):
        resp = self.client.get("/api/csrf-token")
        token = resp.json()["csrf_token"]
        resp = self.client.post("/api/approve", json={
            "spec_id": "SPEC-001", "csrf_token": token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "approved")

    def test_reject_with_valid_csrf(self):
        resp = self.client.get("/api/csrf-token")
        token = resp.json()["csrf_token"]
        resp = self.client.post("/api/reject", json={
            "spec_id": "SPEC-001", "reason": "bad code", "csrf_token": token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "rejected")

    def test_trigger_with_valid_csrf(self):
        resp = self.client.get("/api/csrf-token")
        token = resp.json()["csrf_token"]
        resp = self.client.post("/api/trigger", json={
            "spec_id": "SPEC-001", "csrf_token": token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "triggered")

    def test_kill_with_valid_csrf(self):
        resp = self.client.get("/api/csrf-token")
        token = resp.json()["csrf_token"]
        resp = self.client.post("/api/kill", json={
            "spec_id": "SPEC-001", "csrf_token": token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "killed")

    def test_pause_with_valid_csrf(self):
        resp = self.client.get("/api/csrf-token")
        token = resp.json()["csrf_token"]
        resp = self.client.post("/api/pause", json={"csrf_token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "paused")

    def test_csrf_token_consumed(self):
        resp = self.client.get("/api/csrf-token")
        token = resp.json()["csrf_token"]
        self.client.post("/api/approve", json={"spec_id": "SPEC-001", "csrf_token": token})
        resp2 = self.client.post("/api/approve", json={"spec_id": "SPEC-002", "csrf_token": token})
        self.assertEqual(resp2.status_code, 403)


class TestSSEStream(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_sse_connection(self):
        with self.client.stream("GET", "/api/sse") as resp:
            self.assertEqual(resp.status_code, 200)


class TestCSRFProtectionClass(unittest.TestCase):

    def test_generate_and_verify(self):
        from halo.factory_floor.csrf import CSRFProtection
        csrf = CSRFProtection()
        token = csrf.generate()
        self.assertTrue(csrf.verify(token))
        self.assertFalse(csrf.verify(token))  # consumed

    def test_verify_invalid(self):
        from halo.factory_floor.csrf import CSRFProtection
        csrf = CSRFProtection()
        self.assertFalse(csrf.verify("invalid"))
        self.assertFalse(csrf.verify(""))


if __name__ == '__main__':
    unittest.main()