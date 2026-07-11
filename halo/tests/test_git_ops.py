#!/usr/bin/env python3
"""Unit tests for halo.specs.git_ops and halo.specs.arch_manager."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from halo.specs.git_ops import SpecGitOps
from halo.specs.arch_manager import ArchManager


class TestSpecGitOps(unittest.TestCase):

    @patch("halo.specs.git_ops.GitOps")
    def test_create_spec_branch(self, mock_git_class):
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        ops = SpecGitOps("/repo")
        branch = ops.create_spec_branch("SPEC-001")
        self.assertEqual(branch, "agent/SPEC-001")
        mock_git.create_branch.assert_called_once_with("agent/SPEC-001", base="main")

    @patch("halo.specs.git_ops.GitOps")
    def test_commit_transition(self, mock_git_class):
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        ops = SpecGitOps("/repo")
        msg = ops.commit_transition("SPEC-001", "agent: start")
        self.assertEqual(msg, "agent: start SPEC-001")
        mock_git.commit.assert_called_once_with("agent: start SPEC-001")

    @patch("halo.specs.git_ops.GitOps")
    def test_commit_transition_with_extra(self, mock_git_class):
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        ops = SpecGitOps("/repo")
        msg = ops.commit_transition("SPEC-001", "agent: plan", "plan.md committed")
        self.assertIn("agent: plan SPEC-001", msg)
        self.assertIn("plan.md committed", msg)

    @patch("halo.specs.git_ops.GitOps")
    def test_squash_merge_spec(self, mock_git_class):
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        ops = SpecGitOps("/repo")
        msg = ops.squash_merge_spec("SPEC-001", "AC: test passes")
        mock_git.checkout.assert_called_with("main")
        mock_git.squash_merge.assert_called_once()
        self.assertIn("SPEC-001", msg)
        self.assertIn("Acceptance Criteria", msg)

    @patch("halo.specs.git_ops.GitOps")
    def test_create_snapshot(self, mock_git_class):
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        ops = SpecGitOps("/repo")
        tag = ops.create_snapshot()
        self.assertTrue(tag.startswith("halo-snapshot-"))
        mock_git.create_tag.assert_called_once()

    @patch("halo.specs.git_ops.GitOps")
    def test_create_snapshot_custom_tag(self, mock_git_class):
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        ops = SpecGitOps("/repo")
        tag = ops.create_snapshot("custom-tag")
        self.assertEqual(tag, "custom-tag")

    @patch("halo.specs.git_ops.GitOps")
    def test_delete_spec_branch(self, mock_git_class):
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        mock_git._git.return_value = MagicMock(returncode=0)
        ops = SpecGitOps("/repo")
        result = ops.delete_spec_branch("SPEC-001")
        self.assertTrue(result)


class TestArchManager(unittest.TestCase):

    def test_exists_false(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = ArchManager(d)
            self.assertFalse(mgr.exists())

    def test_ensure_creates(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = ArchManager(d)
            self.assertTrue(mgr.ensure_exists("Demo Project"))
            self.assertTrue(mgr.exists())
            self.assertFalse(mgr.ensure_exists())  # already exists

    def test_write_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = ArchManager(d)
            mgr.write("# Architecture\n\n## Overview\n\nTest\n")
            content = mgr.read()
            self.assertIn("Architecture", content)
            self.assertIn("Overview", content)

    def test_append_section(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = ArchManager(d)
            mgr.write("# Architecture\n")
            mgr.append_section("Decisions", "Use FastAPI")
            content = mgr.read()
            self.assertIn("Decisions", content)
            self.assertIn("Use FastAPI", content)

    def test_get_sections(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = ArchManager(d)
            mgr.write("# Architecture\n\n## Overview\n\nTest overview\n\n## Decisions\n\nUse FastAPI\n")
            sections = mgr.get_sections()
            self.assertIn("Overview", sections)
            self.assertIn("Decisions", sections)
            self.assertIn("FastAPI", sections["Decisions"])

    def test_get_sections_empty(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = ArchManager(d)
            self.assertEqual(mgr.get_sections(), {})


if __name__ == '__main__':
    unittest.main()