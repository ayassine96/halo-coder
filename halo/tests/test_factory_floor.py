#!/usr/bin/env python3
"""Unit tests for Factory Floor dashboard (FF-R1..FF-R7, SEC-6).

Pass 2: Factory Floor is a thin proxy to Supervisor API (:9090).
Tests verify proxy behavior + static file serving.
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient

from halo.factory_floor.app import app, SUPERVISOR_URL
from halo.factory_floor.csrf import CSRFProtection


class TestFactoryFloorStatic(unittest.TestCase):
    """Test static file serving and health."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("supervisor_url", data)

    def test_metrics(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("halo_factory_floor_up", resp.text)

    def test_root_serves_index(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("HALO Factory Floor", resp.text)

    def test_static_css(self):
        resp = self.client.get("/static/styles.css")
        self.assertEqual(resp.status_code, 200)


class TestFactoryFloorProxy(unittest.TestCase):
    """Test API proxy to Supervisor."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("halo.factory_floor.app.httpx.AsyncClient")
    def test_proxy_forwards_get(self, mock_cls):
        """Verify GET /api/* is proxied to Supervisor."""
        mock_inst = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"specs": [], "paused": False}
        mock_inst.get = AsyncMock(return_value=mock_resp)
        mock_inst.request = AsyncMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = self.client.get("/api/state")
        self.assertEqual(resp.status_code, 200)

    @patch("halo.factory_floor.app.httpx.AsyncClient")
    def test_proxy_forwards_post(self, mock_cls):
        """Verify POST /api/* is proxied to Supervisor."""
        mock_inst = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"status": "approved", "spec_id": "SPEC-001"}
        mock_inst.request = AsyncMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = self.client.post("/api/approve", json={"spec_id": "SPEC-001", "csrf_token": "tok"})
        self.assertEqual(resp.status_code, 200)

    @patch("halo.factory_floor.app.httpx.AsyncClient")
    def test_proxy_returns_503_when_supervisor_down(self, mock_cls):
        """Verify 503 when Supervisor is unreachable."""
        import httpx
        mock_inst = AsyncMock()
        mock_inst.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = self.client.get("/api/state")
        self.assertEqual(resp.status_code, 503)
        self.assertIn("Supervisor API unavailable", resp.json()["error"])

    @patch("halo.factory_floor.app.httpx.AsyncClient")
    def test_proxy_forwards_csrf_token(self, mock_cls):
        """Verify /api/csrf-token is proxied."""
        mock_inst = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"csrf_token": "test-token-123"}
        mock_inst.request = AsyncMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = self.client.get("/api/csrf-token")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["csrf_token"], "test-token-123")


class TestCSRFProtectionClass(unittest.TestCase):

    def test_generate_and_verify(self):
        csrf = CSRFProtection()
        token = csrf.generate()
        self.assertTrue(csrf.verify(token))
        self.assertFalse(csrf.verify(token))  # consumed

    def test_verify_invalid(self):
        csrf = CSRFProtection()
        self.assertFalse(csrf.verify("invalid"))
        self.assertFalse(csrf.verify(""))


if __name__ == '__main__':
    unittest.main()