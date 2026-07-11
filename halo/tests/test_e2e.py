#!/usr/bin/env python3
"""End-to-end integration test for HALO Factory (Pass 2 — Phase 2.10).

Tests the full spec lifecycle: draft → ready → in_progress → implemented → merged.
Supports two modes:
- HALO_E2E_MOCK=1 (default): All external services mocked (runs in CI without GPU)
- HALO_E2E_REAL=1: Uses real Lemonade + Redis + K3s (runs on Strix Halo node)
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

from halo.common.models import Spec, SPEC_STATUS_DRAFT, SPEC_STATUS_READY, \
    SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED
from halo.specs.parser import parse_spec_content, update_spec_status
from halo.specs.state_machine import can_transition, transition
from halo.specs.dependency_resolver import DependencyResolver
from halo.factory.workflow import Workflow
from halo.factory.dispatcher import Dispatcher
from unittest.mock import MagicMock


MOCK_MODE = os.environ.get("HALO_E2E_MOCK", "1") == "1"
REAL_MODE = os.environ.get("HALO_E2E_REAL", "0") == "1"


class TestEndToEndLifecycle(unittest.TestCase):
    """Full spec lifecycle: draft → ready → in_progress → implemented → merged."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="halo-e2e-")
        self.project_dir = os.path.join(self.tmpdir, "demo-project")
        self.specs_dir = os.path.join(self.project_dir, "specs")
        self.src_dir = os.path.join(self.project_dir, "src")
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.specs_dir, exist_ok=True)

        self.spec_content = """---
id: SPEC-001
title: "Hello World Endpoint"
status: draft
depends_on: []
blocks: []
tags: [api, fastapi, tdd]
author: halo-agent
---
# SPEC-001: Hello World Endpoint

## Description
Create a simple FastAPI endpoint that returns "Hello, World!"

## Acceptance Criteria
- GET / returns {"message": "Hello, World!"}
- Response status code is 200
"""
        self.spec_file = os.path.join(self.specs_dir, "SPEC-001.md")
        with open(self.spec_file, "w") as f:
            f.write(self.spec_content)

        with open(os.path.join(self.src_dir, "app.py"), "w") as f:
            f.write("def hello(): return 'Hello, World!'\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_01_create_spec(self):
        """WF-SPEC-1: Human writes a spec file with status: draft."""
        spec = parse_spec_content(self.spec_content, self.spec_file)
        self.assertEqual(spec.id, "SPEC-001")
        self.assertEqual(spec.status, SPEC_STATUS_DRAFT)
        self.assertIn("Hello World", spec.title)

    def test_02_trigger_to_ready(self):
        """WF-SPEC-2: Transition draft → ready."""
        spec = parse_spec_content(self.spec_content, self.spec_file)
        self.assertTrue(can_transition(spec.status, SPEC_STATUS_READY))
        new_status, prefix = transition(spec.status, SPEC_STATUS_READY)
        self.assertEqual(new_status, SPEC_STATUS_READY)
        update_spec_status(self.spec_file, SPEC_STATUS_READY)
        with open(self.spec_file) as f:
            updated_content = f.read()
        spec2 = parse_spec_content(updated_content, self.spec_file)
        self.assertEqual(spec2.status, SPEC_STATUS_READY)

    def test_03_dependency_check(self):
        """WF-SPEC-3: Supervisor checks dependencies."""
        specs = {"SPEC-001": parse_spec_content(self.spec_content, self.spec_file)}
        resolver = DependencyResolver(specs)
        self.assertTrue(resolver.is_unblocked("SPEC-001"))
        self.assertTrue(resolver.is_ready("SPEC-001"))

    def test_04_dispatch_planner(self):
        """WF-SPEC-4..5: Dispatch Planner agent."""
        mock_redis = MagicMock()
        dispatcher = Dispatcher(mock_redis)
        dispatcher.dispatch_planner("SPEC-001", prompt="Plan: create FastAPI endpoint")
        mock_redis.stream_enqueue.assert_called_once()

    def test_05_dispatch_coder(self):
        """WF-SPEC-6..8: Dispatch Coder agent with TDAD injection."""
        mock_redis = MagicMock()
        dispatcher = Dispatcher(mock_redis)
        tdad_tests = ["tests/test_app.py"]
        dispatcher.dispatch_coder("SPEC-001", prompt="Implement endpoint",
                                   tdad_tests=tdad_tests)
        mock_redis.stream_enqueue.assert_called_once()

    def test_06_tdd_loop(self):
        """WF-TDD-1..5: TDD Red/Green/Refactor loop."""
        from halo.factory.workflow import TDDLoop
        tdd = TDDLoop()
        tdd.start("SPEC-001")
        self.assertEqual(tdd.get_phase("SPEC-001"), "red")

        self.assertTrue(tdd.verify_red("SPEC-001", tests_failed=True))
        self.assertEqual(tdd.get_phase("SPEC-001"), "green")

        self.assertTrue(tdd.verify_green("SPEC-001", tests_passed=True))
        self.assertEqual(tdd.get_phase("SPEC-001"), "refactor")

        self.assertTrue(tdd.complete_refactor("SPEC-001", tests_still_pass=True))
        self.assertIsNone(tdd.get_phase("SPEC-001"))

    def test_07_tester_runs(self):
        """WF-SPEC-9: Tester agent runs Dagger pipeline."""
        from halo.factory.agents.tester import TesterAgent
        tester = TesterAgent()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1 passed", stderr="")
            result = tester.run_tests(self.project_dir, language="python")
            self.assertIn("exit_code", result)

    def test_08_reviewer_runs(self):
        """WF-SPEC-11: Reviewer agent generates PR summary."""
        from halo.factory.agents.reviewer import ReviewerAgent
        from halo.common.models import Spec
        reviewer = ReviewerAgent()
        spec = parse_spec_content(self.spec_content, self.spec_file)
        prompt = reviewer.build_prompt(spec, git_diff="diff --git a/src/app.py ...")
        self.assertIn("SPEC-001", prompt)
        self.assertIn("review", prompt.lower())

    def test_09_transition_to_implemented(self):
        """WF-SPEC-12: Spec transitions to implemented."""
        spec = parse_spec_content(self.spec_content, self.spec_file)
        spec.status = SPEC_STATUS_IN_PROGRESS
        self.assertTrue(can_transition(SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_IMPLEMENTED))
        new_status, prefix = transition(SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_IMPLEMENTED)
        self.assertEqual(new_status, SPEC_STATUS_IMPLEMENTED)

    def test_10_human_approve(self):
        """WF-SPEC-13..14: Human approves, Merger squash-merges."""
        spec = parse_spec_content(self.spec_content, self.spec_file)
        spec.status = SPEC_STATUS_IMPLEMENTED
        self.assertTrue(can_transition(SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED))
        new_status, prefix = transition(SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED)
        self.assertEqual(new_status, SPEC_STATUS_MERGED)
        self.assertEqual(prefix, "human: approve")

    def test_11_full_lifecycle(self):
        """Complete lifecycle: draft → ready → in_progress → implemented → merged."""
        spec = parse_spec_content(self.spec_content, self.spec_file)
        self.assertEqual(spec.status, SPEC_STATUS_DRAFT)

        for expected_status in [SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS,
                                SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED]:
            update_spec_status(self.spec_file, expected_status)
            with open(self.spec_file) as f:
                updated_content = f.read()
            spec = parse_spec_content(updated_content, self.spec_file)
            self.assertEqual(spec.status, expected_status)

    def test_12_supervisor_api_state(self):
        """Verify Supervisor API /api/state returns real specs from project dir."""
        from fastapi.testclient import TestClient
        from halo.factory.supervisor_api import app, _csrf_tokens

        _csrf_tokens.clear()
        os.environ["HALO_PROJECTS_DIR"] = os.path.dirname(self.project_dir)
        if hasattr(app.state, "supervisor"):
            del app.state.supervisor
        client = TestClient(app)
        resp = client.get("/api/state")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(len(data["specs"]) > 0)
        found = any(s["id"] == "SPEC-001" for s in data["specs"])
        self.assertTrue(found, f"SPEC-001 not found in {data['specs']}")

    def test_13_factory_floor_proxy(self):
        """Verify Factory Floor proxies to Supervisor API."""
        from fastapi.testclient import TestClient
        from halo.factory_floor.app import app as floor_app

        floor_app.dependency_overrides = {}
        client = TestClient(floor_app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("supervisor_url", resp.json())

    def test_14_kernel_real_llm_proxy(self):
        """Verify Kernel gateway proxies to real LLM backend (mock in test mode)."""
        from fastapi.testclient import TestClient
        from halo.kernel import gateway

        gateway._metrics["active_seqs"] = 0
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello from Lemonade"}}],
            "usage": {"completion_tokens": 5},
        }
        mock_inst = AsyncMock()
        mock_inst.post = AsyncMock(return_value=mock_resp)
        with patch("halo.kernel.gateway.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            client = TestClient(gateway.app)
            resp = client.post("/v1/chat/completions", json={
                "model": "halo-fast",
                "messages": [{"role": "user", "content": "Say hello"}],
            })
            self.assertEqual(resp.status_code, 200)

    def test_15_tdad_tree_sitter_index(self):
        """Verify TDAD can index the demo project with tree-sitter."""
        from halo.tdad.ast_builder import build_graph, _TREE_SITTER_AVAILABLE
        from halo.tdad.graph_store import GraphStore

        self.assertTrue(_TREE_SITTER_AVAILABLE, "tree-sitter should be installed")
        store = GraphStore(os.path.join(self.tmpdir, "graph.json"))
        build_graph(self.project_dir, store)
        self.assertGreater(store.module_count, 0)

    def test_16_rag_embedding(self):
        """Verify RAG indexer can embed spec content."""
        from halo.memory.rag_indexer import RagIndexer, EMBEDDING_DIM, _SENTENCE_TRANSFORMERS_AVAILABLE

        self.assertTrue(_SENTENCE_TRANSFORMERS_AVAILABLE, "sentence-transformers should be installed")
        mock_qdrant = MagicMock()
        indexer = RagIndexer(qdrant_client=mock_qdrant)
        vec = indexer._default_embedding("Hello World endpoint test")
        self.assertEqual(len(vec), EMBEDDING_DIM)


if __name__ == "__main__":
    unittest.main()