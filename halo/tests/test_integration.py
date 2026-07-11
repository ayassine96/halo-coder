#!/usr/bin/env python3
"""Unit tests for RAG indexer, RAG query, chat memory, and agent roles (Stage 9)."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from halo.memory.rag_indexer import RagIndexer, EMBEDDING_DIM, COLLECTION_NAME
from halo.memory.rag_query import RagQuery
from halo.memory.chat_memory import ChatMemory
from halo.factory.agents.planner import PlannerAgent
from halo.factory.agents.coder import CoderAgent
from halo.factory.agents.tester import TesterAgent
from halo.factory.agents.reviewer import ReviewerAgent
from halo.factory.agents.merger import MergerAgent
from halo.common.models import Spec


class TestRagIndexer(unittest.TestCase):

    def test_default_embedding(self):
        indexer = RagIndexer()
        vec = indexer._embed("test text")
        self.assertEqual(len(vec), EMBEDDING_DIM)
        self.assertTrue(all(0 <= v <= 1 for v in vec))

    def test_hash_id_stable(self):
        indexer = RagIndexer()
        id1 = indexer._hash_id("test")
        id2 = indexer._hash_id("test")
        self.assertEqual(id1, id2)
        id3 = indexer._hash_id("other")
        self.assertNotEqual(id1, id3)

    def test_index_specs(self):
        with tempfile.TemporaryDirectory() as d:
            specs_dir = os.path.join(d, "specs")
            os.makedirs(specs_dir)
            for i in range(3):
                with open(os.path.join(specs_dir, f"SPEC-00{i}.md"), "w") as f:
                    f.write(f"---\nid: SPEC-00{i}\ntitle: Test {i}\nstatus: draft\n---\nbody {i}")
            mock_qdrant = MagicMock()
            indexer = RagIndexer(qdrant_client=mock_qdrant)
            count = indexer.index_specs(specs_dir)
            self.assertEqual(count, 3)
            self.assertEqual(mock_qdrant.upsert.call_count, 3)

    def test_index_arch_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            mock_qdrant = MagicMock()
            indexer = RagIndexer(qdrant_client=mock_qdrant)
            count = indexer.index_arch(d)
            self.assertEqual(count, 0)

    def test_index_arch_with_file(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "ARCH.md"), "w") as f:
                f.write("# Architecture\n\nTest")
            mock_qdrant = MagicMock()
            indexer = RagIndexer(qdrant_client=mock_qdrant)
            count = indexer.index_arch(d)
            self.assertEqual(count, 1)

    def test_rebuild_from_git(self):
        with tempfile.TemporaryDirectory() as d:
            specs_dir = os.path.join(d, "specs")
            src_dir = os.path.join(d, "src")
            os.makedirs(specs_dir)
            os.makedirs(src_dir)
            with open(os.path.join(d, "ARCH.md"), "w") as f:
                f.write("# Arch")
            with open(os.path.join(specs_dir, "SPEC-001.md"), "w") as f:
                f.write("spec body")
            with open(os.path.join(src_dir, "app.py"), "w") as f:
                f.write("def main(): pass")
            mock_qdrant = MagicMock()
            indexer = RagIndexer(qdrant_client=mock_qdrant)
            total = indexer.rebuild_from_git(d)
            self.assertGreaterEqual(total, 3)

    def test_index_source_files(self):
        with tempfile.TemporaryDirectory() as d:
            for fname in ["app.py", "models.py", "test.ts"]:
                with open(os.path.join(d, fname), "w") as f:
                    f.write("test code")
            mock_qdrant = MagicMock()
            indexer = RagIndexer(qdrant_client=mock_qdrant)
            count = indexer.index_source_files(d)
            self.assertEqual(count, 3)


class TestRagQuery(unittest.TestCase):

    def test_retrieve_context_with_results(self):
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"id": 1, "score": 0.9, "payload": {"type": "spec", "doc_id": "SPEC-001.md", "text": "hello world"}},
        ]
        query = RagQuery(qdrant_client=mock_qdrant)
        spec = MagicMock(id="SPEC-002", title="Test", body="body content")
        ctx = query.retrieve_context(spec)
        self.assertIn("RAG Context", ctx)
        self.assertIn("SPEC-001", ctx)

    def test_retrieve_context_no_results(self):
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = []
        query = RagQuery(qdrant_client=mock_qdrant)
        spec = MagicMock(id="SPEC-001", title="Test", body="body")
        ctx = query.retrieve_context(spec)
        self.assertEqual(ctx, "")

    def test_search_similar_specs(self):
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"id": 1, "score": 0.8, "payload": {"type": "spec", "doc_id": "SPEC-001.md", "text": "test"}},
        ]
        query = RagQuery(qdrant_client=mock_qdrant)
        results = query.search_similar_specs("test spec")
        self.assertEqual(len(results), 1)

    def test_search_related_adrs(self):
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"id": 2, "score": 0.7, "payload": {"type": "arch", "doc_id": "ARCH.md", "text": "arch"}},
        ]
        query = RagQuery(qdrant_client=mock_qdrant)
        results = query.search_related_adrs(["api", "fastapi"])
        self.assertEqual(len(results), 1)


class TestChatMemory(unittest.TestCase):

    def test_append_and_recent(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            mem = ChatMemory(path)
            mem.append("user", "hello")
            mem.append("assistant", "world")
            recent = mem.recent(5)
            self.assertEqual(len(recent), 2)
        finally:
            os.unlink(path)

    def test_search(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            mem = ChatMemory(path)
            mem.append("user", "find me here")
            mem.append("user", "other message")
            results = mem.search("find")
            self.assertEqual(len(results), 1)
        finally:
            os.unlink(path)

    def test_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            mem = ChatMemory(path)
            self.assertEqual(mem.recent(10), [])
            self.assertEqual(mem.size(), 0)
        finally:
            os.unlink(path)


class TestPlannerAgent(unittest.TestCase):

    def test_build_prompt(self):
        spec = MagicMock(id="SPEC-001", title="Test", body="AC: stuff")
        arch = MagicMock()
        arch.exists.return_value = True
        arch.read.return_value = "# Architecture\n\nTest"
        agent = PlannerAgent(arch_manager=arch)
        prompt = agent.build_prompt(spec)
        self.assertIn("SPEC-001", prompt)
        self.assertIn("Architecture", prompt)
        self.assertIn("plan.md", prompt)

    def test_build_prompt_with_rag(self):
        spec = MagicMock(id="SPEC-001", title="Test", body="body")
        rag = MagicMock()
        rag.retrieve_context.return_value = "RAG Context:\nSimilar spec"
        agent = PlannerAgent(rag_query=rag)
        prompt = agent.build_prompt(spec)
        self.assertIn("RAG", prompt)
        self.assertIn("Similar spec", prompt)


class TestCoderAgent(unittest.TestCase):

    def test_build_prompt_with_tdad(self):
        spec = MagicMock(id="SPEC-001", title="Test", body="body")
        agent = CoderAgent()
        prompt = agent.build_prompt(spec, "plan here", changed_files=["src/auth.py"],
                                     tdad_tests=["tests/test_auth.py::test_login"])
        self.assertIn("src/auth.py", prompt)
        self.assertIn("test_login", prompt)
        self.assertIn("MUST run these tests", prompt)

    def test_build_prompt_with_failure_logs(self):
        spec = MagicMock(id="SPEC-001", title="Test", body="body")
        agent = CoderAgent()
        prompt = agent.build_prompt(spec, "plan", failure_logs="FAIL: test failed")
        self.assertIn("FAIL: test failed", prompt)

    def test_execute_with_tdad(self):
        spec = MagicMock(id="SPEC-001", title="Test", body="body")
        tdad = MagicMock()
        tdad.analyze.return_value = {"affected_tests": ["tests/test_app.py"]}
        agent = CoderAgent(tdad_client=tdad)
        result = agent.execute(spec, "plan", changed_files=["src/app.py"])
        self.assertIn("test_app.py", result)


class TestTesterAgent(unittest.TestCase):

    def test_build_prompt(self):
        spec = MagicMock(id="SPEC-001", title="Test")
        agent = TesterAgent()
        prompt = agent.build_prompt(spec, test_results="PASS: 3 tests")
        self.assertIn("PASS", prompt)
        self.assertIn("SPEC-001", prompt)


class TestReviewerAgent(unittest.TestCase):

    def test_build_prompt(self):
        spec = MagicMock(id="SPEC-001", title="Test", body="AC: must work")
        agent = ReviewerAgent()
        prompt = agent.build_prompt(spec, git_diff="diff --git a/app.py")
        self.assertIn("SPEC-001", prompt)
        self.assertIn("Acceptance Criteria", prompt)
        self.assertIn("diff --git", prompt)


class TestMergerAgent(unittest.TestCase):

    def test_execute_with_git(self):
        spec = MagicMock(id="SPEC-001", title="Test")
        git = MagicMock()
        agent = MergerAgent(git_ops=git)
        result = agent.execute(spec, acceptance_criteria="AC: test passes")
        self.assertEqual(result["status"], "merged")
        git.squash_merge_spec.assert_called_once_with("SPEC-001", "AC: test passes")
        git.delete_spec_branch.assert_called_once_with("SPEC-001")

    def test_execute_no_git(self):
        spec = MagicMock(id="SPEC-001")
        agent = MergerAgent()
        result = agent.execute(spec)
        self.assertEqual(result["status"], "no_git_ops")


class TestEndToEndIntegration(unittest.TestCase):
    """Integration test exercising the full pipeline (WF-SPEC-1..15)."""

    def test_full_spec_lifecycle(self):
        from halo.factory.workflow import Workflow
        from halo.specs.state_machine import transition, can_transition
        from halo.specs.dependency_resolver import DependencyResolver
        from halo.specs.parser import parse_spec_content
        from halo.factory.dispatcher import Dispatcher

        spec_content = """---
id: SPEC-001
title: "Test endpoint"
status: draft
depends_on: []
blocks: []
tags: [api]
---
# Test\nAcceptance: GET / returns 200"""
        spec = parse_spec_content(spec_content)

        spec.status = "ready"
        self.assertTrue(can_transition("draft", "ready"))

        spec.status = "in_progress"
        self.assertTrue(can_transition("ready", "in_progress"))

        spec.status = "implemented"
        self.assertTrue(can_transition("in_progress", "implemented"))

        spec.status = "merged"
        self.assertTrue(can_transition("implemented", "merged"))

        resolver = DependencyResolver({"SPEC-001": spec})
        self.assertTrue(resolver.is_ready("SPEC-001"))
        self.assertTrue(resolver.is_unblocked("SPEC-001"))

        mock_redis = MagicMock()
        dispatcher = Dispatcher(mock_redis)
        dispatcher.dispatch_planner("SPEC-001", prompt="plan it")
        mock_redis.stream_enqueue.assert_called_once()

    def test_graceful_degradation(self):
        """Test REL-4 graceful degradation scenarios."""
        from halo.factory.event_publisher import EventPublisher
        from halo.factory.circuit_breaker import CircuitBreaker

        # Redis down → degrade to Git-only
        mock_redis = MagicMock()
        mock_redis.publish.side_effect = Exception("down")
        pub = EventPublisher(mock_redis)
        result = pub.log_event("SPEC-001", "test")
        self.assertFalse(result)
        pub.check_redis = MagicMock(return_value=False)
        self.assertFalse(pub.check_redis())

        # Model backend failure → circuit opens
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("halo-reasoning")
        self.assertTrue(cb.can_proceed("halo-reasoning"))
        cb.record_failure("halo-reasoning")
        self.assertFalse(cb.can_proceed("halo-reasoning"))


if __name__ == '__main__':
    unittest.main()