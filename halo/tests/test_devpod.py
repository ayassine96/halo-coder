#!/usr/bin/env python3
"""Unit tests for Agent-Bridge and Nanoclaw (Stage 7 — AB-R1..R5, DP-R8)."""

import os
import json
import tempfile
import unittest

from halo.nanoclaw.memory import MemoryFile, ROTATE_SIZE
from halo.nanoclaw.server import NanoclawServer


class TestMemoryFile(unittest.TestCase):

    def test_append_and_read(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            mem = MemoryFile(path)
            mem.append({"role": "user", "content": "hello"})
            mem.append({"role": "assistant", "content": "world"})
            entries = mem.read_all()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["content"], "hello")
            self.assertEqual(entries[1]["content"], "world")
        finally:
            os.unlink(path)

    def test_read_recent(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            mem = MemoryFile(path)
            for i in range(20):
                mem.append({"i": i})
            recent = mem.read_recent(count=5)
            self.assertEqual(len(recent), 5)
            self.assertEqual(recent[-1]["i"], 19)
        finally:
            os.unlink(path)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            mem = MemoryFile(path)
            self.assertEqual(mem.read_all(), [])
            self.assertEqual(mem.size(), 0)
        finally:
            os.unlink(path)

    def test_rotation(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            mem = MemoryFile(path)
            # Write enough data to exceed the rotation threshold using a smaller threshold
            import halo.nanoclaw.memory as mem_mod
            original = mem_mod.ROTATE_SIZE
            mem_mod.ROTATE_SIZE = 100
            for i in range(20):
                mem.append({"i": i, "content": "x" * 50})
            self.assertTrue(os.path.exists(path + ".1"))
            mem_mod.ROTATE_SIZE = original
        finally:
            for p in [path, path + ".1"]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_clear(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            mem = MemoryFile(path)
            mem.append({"test": True})
            mem.clear()
            self.assertFalse(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestNanoclawServer(unittest.TestCase):

    def test_process_health(self):
        server = NanoclawServer(sock_path="/tmp/test-nanoclaw.sock",
                                 memory_path=tempfile.mktemp(suffix=".jsonl"))
        result = server._process({"action": "health"})
        self.assertEqual(result["status"], "ok")

    def test_process_memory_append_read(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            server = NanoclawServer(sock_path="/tmp/test-nanoclaw.sock", memory_path=path)
            server._process({"action": "memory_append", "entry": {"role": "user", "content": "test"}})
            result = server._process({"action": "memory_read", "count": 5})
            self.assertEqual(len(result["entries"]), 1)
            self.assertEqual(result["entries"][0]["content"], "test")
        finally:
            os.unlink(path)

    def test_process_unknown_action(self):
        server = NanoclawServer(sock_path="/tmp/test-nanoclaw.sock",
                                 memory_path=tempfile.mktemp(suffix=".jsonl"))
        result = server._process({"action": "bogus"})
        self.assertIn("error", result)


class TestAgentBridge(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from halo.agent_bridge.app import app
        import halo.agent_bridge.app as ab_app
        ab_app._project_dir = "/tmp"
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_files(self):
        resp = self.client.get("/api/files")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("items", resp.json())

    def test_launchers(self):
        resp = self.client.get("/api/launchers")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("terminal", data)
        self.assertIn("vscode", data)

    def test_chat(self):
        import halo.agent_bridge.app as ab_app
        original = ab_app._send_to_nanoclaw
        async def mock_send(msg):
            return "mock response"
        ab_app._send_to_nanoclaw = mock_send
        resp = self.client.post("/api/chat", json={"message": "hello"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("response", resp.json())
        ab_app._send_to_nanoclaw = original


if __name__ == '__main__':
    unittest.main()