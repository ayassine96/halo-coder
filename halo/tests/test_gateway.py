#!/usr/bin/env python3
"""Unit tests for HALO Kernel gateway (HK-R1..HK-R5)."""

import unittest
from unittest.mock import patch, MagicMock

from halo.kernel.vllm_config import MODEL_PROFILES, get_vllm_args, build_launch_command


class TestModelProfiles(unittest.TestCase):

    def test_profiles_exist(self):
        self.assertIn("halo-fast", MODEL_PROFILES)
        self.assertIn("halo-reasoning", MODEL_PROFILES)
        self.assertIn("halo-vision", MODEL_PROFILES)

    def test_fast_profile(self):
        p = MODEL_PROFILES["halo-fast"]
        self.assertEqual(p["max_num_seqs"], 8)
        self.assertLess(p["gpu_memory_utilization"], 0.2)

    def test_reasoning_profile(self):
        p = MODEL_PROFILES["halo-reasoning"]
        self.assertLessEqual(p["max_num_seqs"], 4)
        self.assertGreater(p["gpu_memory_utilization"], 0.5)

    def test_total_vram(self):
        total = sum(p["gpu_memory_utilization"] * 60 for p in MODEL_PROFILES.values())
        self.assertLessEqual(total, 60, "Total VRAM allocation exceeds 60GB limit")

    def test_get_vllm_args(self):
        args = get_vllm_args("halo-fast")
        self.assertIn("model", args)
        self.assertIn("max-num-seqs", args)
        self.assertEqual(args["port"], 13305)

    def test_build_launch_command(self):
        cmd = build_launch_command("halo-fast")
        self.assertIn("vllm.entrypoints.openai.api_server", cmd)


class TestGatewayEndpoints(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from halo.kernel.gateway import app
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("halo-fast", data["models"])

    def test_list_models(self):
        resp = self.client.get("/v1/models")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        ids = [m["id"] for m in data["data"]]
        self.assertIn("halo-fast", ids)
        self.assertIn("halo-reasoning", ids)

    def test_metrics(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertIn("halo_kernel_requests_total", text)
        self.assertIn("halo_kernel_vram_limit_gb", text)


class TestAdmissionControl(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from halo.kernel import gateway
        self.gateway = gateway
        self.client = TestClient(gateway.app)
        self.gateway._metrics["active_seqs"] = 0
        self.gateway._metrics["requests_total"] = 0
        self.gateway._metrics["admissions_queued"] = 0

    def test_request_accepted_under_limit(self):
        self.gateway._metrics["active_seqs"] = 0
        resp = self.client.post("/v1/chat/completions", json={"model": "halo-fast", "messages": []})
        self.assertEqual(resp.status_code, 200)

    def test_request_queued_at_limit(self):
        self.gateway._metrics["active_seqs"] = 8  # max for halo-fast
        resp = self.client.post("/v1/chat/completions", json={"model": "halo-fast", "messages": []})
        self.assertEqual(resp.status_code, 202)
        self.assertIn("Retry-After", resp.headers)
        self.assertGreater(int(resp.headers["Retry-After"]), 0)

    def test_unknown_model_rejected(self):
        resp = self.client.post("/v1/chat/completions", json={"model": "nonexistent", "messages": []})
        self.assertEqual(resp.status_code, 400)


if __name__ == '__main__':
    unittest.main()