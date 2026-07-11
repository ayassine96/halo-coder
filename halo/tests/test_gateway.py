#!/usr/bin/env python3
"""Unit tests for HALO Kernel gateway (HK-R1..HK-R5)."""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from halo.kernel.vllm_config import MODEL_PROFILES, get_vllm_args, build_launch_command


class TestModelProfiles(unittest.TestCase):

    def test_profiles_exist(self):
        self.assertIn("halo-fast", MODEL_PROFILES)
        self.assertIn("halo-reasoning", MODEL_PROFILES)
        self.assertIn("halo-vision", MODEL_PROFILES)

    def test_coder_profile_exists(self):
        self.assertIn("halo-coder", MODEL_PROFILES)

    def test_fast_profile(self):
        p = MODEL_PROFILES["halo-fast"]
        self.assertEqual(p["max_num_seqs"], 8)
        self.assertLess(p["gpu_memory_utilization"], 0.2)

    def test_reasoning_profile(self):
        p = MODEL_PROFILES["halo-reasoning"]
        self.assertLessEqual(p["max_num_seqs"], 4)
        self.assertGreater(p["gpu_memory_utilization"], 0.5)

    def test_backend_model_set(self):
        for name, p in MODEL_PROFILES.items():
            self.assertIn("backend_model", p, f"{name} missing backend_model")

    def test_each_profile_vram_within_limit(self):
        """With Lemonade, models load on demand (one at a time), not all simultaneously.
        Each profile's VRAM allocation must fit within the 60GB limit."""
        for name, p in MODEL_PROFILES.items():
            vram = p["gpu_memory_utilization"] * 60
            self.assertLessEqual(vram, 60, f"{name} VRAM {vram}GB exceeds 60GB limit")

    def test_get_vllm_args(self):
        args = get_vllm_args("halo-fast")
        self.assertIn("model", args)
        self.assertIn("max-num-seqs", args)

    def test_build_launch_command(self):
        cmd = build_launch_command("halo-fast")
        self.assertIn("vllm.entrypoints.openai.api_server", cmd)


def _mock_backend_response(model="halo-reasoning", content="Hello from Lemonade"):
    """Create a mock httpx response from the LLM backend."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    return mock_resp


class TestGatewayEndpoints(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from halo.kernel import gateway
        self.gateway = gateway
        self.client = TestClient(gateway.app)
        self.gateway._metrics["active_seqs"] = 0
        self.gateway._metrics["requests_total"] = 0
        self.gateway._metrics["admissions_queued"] = 0
        self.gateway._metrics["tokens_total"] = 0

    @patch("halo.kernel.gateway._check_backend", new_callable=AsyncMock, return_value=True)
    def test_health(self, _):
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
        self.assertIn("halo-coder", ids)

    def test_metrics(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertIn("halo_kernel_requests_total", text)
        self.assertIn("halo_kernel_vram_limit_gb", text)


class TestChatCompletions(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from halo.kernel import gateway
        self.gateway = gateway
        self.client = TestClient(gateway.app)
        self.gateway._metrics["active_seqs"] = 0
        self.gateway._metrics["requests_total"] = 0
        self.gateway._metrics["tokens_total"] = 0

    @patch("halo.kernel.gateway.httpx.AsyncClient")
    def test_chat_completion_proxies_to_backend(self, mock_client_cls):
        """Verify gateway proxies to LLM backend and returns its response."""
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=_mock_backend_response())
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = self.client.post("/v1/chat/completions", json={
            "model": "halo-reasoning",
            "messages": [{"role": "user", "content": "hello"}],
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("choices", data)
        self.assertEqual(data["choices"][0]["message"]["content"], "Hello from Lemonade")

    @patch("halo.kernel.gateway.httpx.AsyncClient")
    def test_model_name_translated(self, mock_client_cls):
        """Verify HALO profile name is translated to backend model ID."""
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=_mock_backend_response())
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        self.client.post("/v1/chat/completions", json={
            "model": "halo-fast",
            "messages": [{"role": "user", "content": "hi"}],
        })
        call_args = mock_instance.post.call_args
        sent_body = call_args.kwargs["json"]
        self.assertEqual(sent_body["model"], "Qwen3-8B-GGUF")

    @patch("halo.kernel.gateway.httpx.AsyncClient")
    def test_tokens_tracked_in_metrics(self, mock_client_cls):
        """Verify completion tokens are tracked in metrics."""
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=_mock_backend_response())
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        self.client.post("/v1/chat/completions", json={
            "model": "halo-fast",
            "messages": [{"role": "user", "content": "hi"}],
        })
        self.assertGreater(self.gateway._metrics["tokens_total"], 0)

    def test_unknown_model_rejected(self):
        resp = self.client.post("/v1/chat/completions", json={"model": "nonexistent", "messages": []})
        self.assertEqual(resp.status_code, 400)


class TestAdmissionControl(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from halo.kernel import gateway
        self.gateway = gateway
        self.client = TestClient(gateway.app)
        self.gateway._metrics["active_seqs"] = 0
        self.gateway._metrics["requests_total"] = 0
        self.gateway._metrics["admissions_queued"] = 0

    @patch("halo.kernel.gateway.httpx.AsyncClient")
    def test_request_accepted_under_limit(self, mock_client_cls):
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=_mock_backend_response())
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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


class TestBackendUnavailable(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from halo.kernel import gateway
        self.gateway = gateway
        self.client = TestClient(gateway.app)
        self.gateway._metrics["active_seqs"] = 0
        self.gateway._metrics["requests_total"] = 0

    @patch("halo.kernel.gateway.httpx.AsyncClient")
    def test_backend_connect_error_returns_503(self, mock_client_cls):
        """If backend is unreachable, gateway returns 503 with Retry-After."""
        import httpx
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = self.client.post("/v1/chat/completions", json={
            "model": "halo-fast",
            "messages": [{"role": "user", "content": "hi"}],
        })
        self.assertEqual(resp.status_code, 503)
        self.assertIn("Retry-After", resp.headers)

    @patch("halo.kernel.gateway.httpx.AsyncClient")
    def test_backend_timeout_returns_504(self, mock_client_cls):
        """If backend times out, gateway returns 504 with Retry-After."""
        import httpx
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = self.client.post("/v1/chat/completions", json={
            "model": "halo-fast",
            "messages": [{"role": "user", "content": "hi"}],
        })
        self.assertEqual(resp.status_code, 504)
        self.assertIn("Retry-After", resp.headers)


if __name__ == '__main__':
    unittest.main()