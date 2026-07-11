#!/usr/bin/env python3
"""Unit tests for TDAD service (TDAD-R1..R6)."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from halo.tdad.graph_store import GraphStore
from halo.tdad.ast_builder import (
    parse_imports, parse_defs, is_test_file, build_graph, analyze_changed_files,
)
from halo.tdad.incremental import incremental_update, full_reindex


class TestGraphStore(unittest.TestCase):

    def setUp(self):
        self.store = GraphStore("/tmp/test-halo-graph.json")

    def test_add_module(self):
        self.store.add_module("src/auth.py", imports=["os"], defs=["login"])
        self.assertEqual(self.store.module_count, 1)
        self.assertIn("src/auth.py", self.store._modules)

    def test_add_test(self):
        self.store.add_test("tests/test_auth.py", targets=["src.auth"])
        self.assertEqual(self.store.test_count, 1)

    def test_add_edge(self):
        self.store.add_edge("src/auth.py", "tests/test_auth.py")
        self.assertEqual(self.store.edge_count, 1)

    def test_get_affected_tests(self):
        self.store.add_edge("src/auth.py", "tests/test_auth.py")
        self.store.add_edge("src/auth.py", "tests/test_api.py")
        affected = self.store.get_affected_tests(["src/auth.py"])
        self.assertIn("tests/test_auth.py", affected)
        self.assertIn("tests/test_api.py", affected)

    def test_get_uncovered(self):
        self.store.add_edge("src/auth.py", "tests/test_auth.py")
        uncovered = self.store.get_uncovered_paths(["src/auth.py", "src/no_tests.py"])
        self.assertIn("src/no_tests.py", uncovered)
        self.assertNotIn("src/auth.py", uncovered)

    def test_save_load(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = GraphStore(path)
            store.add_module("src/app.py", imports=["fastapi"], defs=["create_app"])
            store.add_test("tests/test_app.py", targets=["src.app"])
            store.add_edge("src/app.py", "tests/test_app.py")
            store.save()

            store2 = GraphStore(path)
            store2.load()
            self.assertEqual(store2.module_count, 1)
            self.assertEqual(store2.test_count, 1)
            self.assertEqual(store2.edge_count, 1)
        finally:
            os.unlink(path)


class TestAstBuilder(unittest.TestCase):

    def test_parse_imports(self):
        content = "import os\nfrom fastapi import FastAPI\nfrom halo.common import models"
        imports = parse_imports(content)
        self.assertIn("os", imports)
        self.assertIn("fastapi", imports)
        self.assertIn("halo.common", imports)

    def test_parse_defs(self):
        content = "def hello():\n    pass\n\nclass MyModel:\n    pass"
        defs = parse_defs(content)
        self.assertIn("hello", defs)
        self.assertIn("MyModel", defs)

    def test_is_test_file(self):
        self.assertTrue(is_test_file("tests/test_auth.py"))
        self.assertFalse(is_test_file("src/auth.py"))

    def test_build_graph(self):
        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, "src"))
            os.makedirs(os.path.join(repo, "tests"))
            with open(os.path.join(repo, "src", "auth.py"), "w") as f:
                f.write("def login():\n    pass\n")
            with open(os.path.join(repo, "tests", "test_auth.py"), "w") as f:
                f.write("from src.auth import login\n\ndef test_login():\n    pass\n")

            store = GraphStore("/tmp/test-tdad-graph.json")
            build_graph(repo, store)
            self.assertGreater(store.module_count, 0)
            self.assertGreater(store.test_count, 0)


class TestAnalyzeChangedFiles(unittest.TestCase):

    def test_analyze_with_edge(self):
        store = GraphStore("/tmp/test-tdad-2.json")
        store.add_edge("src/auth.py", "tests/test_auth.py")
        affected, conf, uncovered = analyze_changed_files(".", ["src/auth.py"], store)
        self.assertIn("tests/test_auth.py", affected)

    def test_analyze_no_tests(self):
        store = GraphStore("/tmp/test-tdad-3.json")
        affected, conf, uncovered = analyze_changed_files(".", ["src/nothing.py"], store)
        self.assertEqual(affected, [])
        self.assertIn("src/nothing.py", uncovered)


class TestIncremental(unittest.TestCase):

    def test_incremental_update(self):
        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, "src"))
            store = GraphStore("/tmp/test-tdad-incr.json")
            store.add_module("src/old.py")
            incremental_update(repo, [], store)

    def test_full_reindex(self):
        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, "src"))
            os.makedirs(os.path.join(repo, "tests"))
            with open(os.path.join(repo, "src", "app.py"), "w") as f:
                f.write("def main():\n    pass\n")
            with open(os.path.join(repo, "tests", "test_app.py"), "w") as f:
                f.write("from src.app import main\n")
            store = GraphStore("/tmp/test-tdad-reindex.json")
            mods, tests = full_reindex(repo, store)
            self.assertGreater(mods, 0)


class TestTdadApp(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from halo.tdad.app import app
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("status", resp.json())

    def test_metrics(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("halo_tdad_modules", resp.text)

    def test_analyze_empty(self):
        resp = self.client.post("/analyze", json={"repo": "/nonexistent", "changed_files": []})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["affected_tests"], [])

    def test_analyze_with_files(self):
        resp = self.client.post("/analyze", json={
            "repo": "/nonexistent",
            "changed_files": ["src/auth.py"],
            "spec_id": "SPEC-001"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("confidence", data)


class TestDaggerPipelines(unittest.TestCase):

    def test_python_pipeline_spec(self):
        from halo.dagger.pipelines.python_test import build_dagger_python_pipeline
        spec = build_dagger_python_pipeline("/repo", run_ruff=True)
        self.assertEqual(spec["pipeline"], "python-test")
        self.assertTrue(spec["mount"]["read_only"])
        step_names = [s["name"] for s in spec["steps"]]
        self.assertIn("pytest", step_names)
        self.assertIn("ruff", step_names)

    def test_node_pipeline_spec(self):
        from halo.dagger.pipelines.node_test import build_dagger_node_pipeline
        spec = build_dagger_node_pipeline("/repo", runner="yarn")
        self.assertEqual(spec["pipeline"], "node-test")

    def test_e2e_pipeline_spec(self):
        from halo.dagger.pipelines.e2e_test import build_dagger_e2e_pipeline
        spec = build_dagger_e2e_pipeline("/repo")
        self.assertEqual(spec["pipeline"], "e2e-playwright")
        self.assertIn("playwright", spec["container_image"])

    def test_engine_config(self):
        from halo.dagger.engine_config import build_pipeline_config
        cfg = build_pipeline_config(cpu=2, ram=4)
        self.assertEqual(cfg["cpu_limit"], "2")
        self.assertIn("Gi", cfg["ram_limit"])


class TestArtifactStore(unittest.TestCase):

    def test_upload_junit(self):
        mock_minio = MagicMock()
        store = type("S", (), {"minio": mock_minio, "bucket": "halo"})()
        from halo.dagger.artifact_store import ArtifactStore
        as_ = ArtifactStore(mock_minio)
        path = as_.upload_junit("demo", "SPEC-001", "<xml>test</xml>")
        self.assertIn("artifacts/demo/SPEC-001/junit.xml", path)
        mock_minio.upload.assert_called_once()

    def test_download(self):
        mock_minio = MagicMock()
        mock_minio.download.return_value = b"<xml>test</xml>"
        from halo.dagger.artifact_store import ArtifactStore
        as_ = ArtifactStore(mock_minio)
        data = as_.download("demo", "SPEC-001", "junit.xml")
        self.assertEqual(data, b"<xml>test</xml>")

    def test_list_artifacts(self):
        mock_minio = MagicMock()
        mock_obj = MagicMock()
        mock_obj.object_name = "artifacts/demo/SPEC-001/junit.xml"
        mock_minio.list_objects.return_value = [mock_obj]
        from halo.dagger.artifact_store import ArtifactStore
        as_ = ArtifactStore(mock_minio)
        artifacts = as_.list_artifacts("demo", "SPEC-001")
        self.assertEqual(len(artifacts), 1)


if __name__ == '__main__':
    unittest.main()