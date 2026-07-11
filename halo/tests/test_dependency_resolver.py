#!/usr/bin/env python3
"""Unit tests for halo.specs.dependency_resolver (OR-R3, OR-R4)."""

import unittest

from halo.specs.dependency_resolver import DependencyResolver, CycleError
from halo.common.models import Spec


def make_spec(spec_id, status="draft", depends_on=None, blocks=None):
    return Spec(
        id=spec_id, title=f"Test {spec_id}", status=status,
        depends_on=depends_on or [], blocks=blocks or [],
    )


class TestDependencyReady(unittest.TestCase):

    def setUp(self):
        self.specs = {
            "SPEC-001": make_spec("SPEC-001", status="draft", depends_on=["SPEC-002"]),
            "SPEC-002": make_spec("SPEC-002", status="implemented"),
        }
        self.resolver = DependencyResolver(self.specs)

    def test_is_ready_when_deps_implemented(self):
        self.assertTrue(self.resolver.is_ready("SPEC-001"))

    def test_not_ready_when_deps_not_implemented(self):
        self.specs["SPEC-002"].status = "draft"
        self.assertFalse(self.resolver.is_ready("SPEC-001"))

    def test_not_ready_when_dep_missing(self):
        self.specs["SPEC-001"].depends_on = ["SPEC-999"]
        self.assertFalse(self.resolver.is_ready("SPEC-001"))

    def test_ready_when_dep_merged(self):
        self.specs["SPEC-002"].status = "merged"
        self.assertTrue(self.resolver.is_ready("SPEC-001"))

    def test_ready_no_deps(self):
        self.specs["SPEC-002"].depends_on = []
        self.assertTrue(self.resolver.is_ready("SPEC-002"))


class TestBlocking(unittest.TestCase):

    def setUp(self):
        self.specs = {
            "SPEC-001": make_spec("SPEC-001", status="in_progress", blocks=["SPEC-002"]),
            "SPEC-002": make_spec("SPEC-002", status="ready"),
        }
        self.resolver = DependencyResolver(self.specs)

    def test_blocked_when_blocker_in_progress(self):
        self.assertFalse(self.resolver.is_unblocked("SPEC-002"))

    def test_unblocked_when_blocker_implemented(self):
        self.specs["SPEC-001"].status = "implemented"
        self.assertTrue(self.resolver.is_unblocked("SPEC-002"))

    def test_can_start(self):
        self.assertFalse(self.resolver.can_start("SPEC-002"))
        self.specs["SPEC-001"].status = "implemented"
        self.assertTrue(self.resolver.can_start("SPEC-002"))


class TestTopologicalSort(unittest.TestCase):

    def test_simple_order(self):
        specs = {
            "SPEC-003": make_spec("SPEC-003", depends_on=["SPEC-002"]),
            "SPEC-002": make_spec("SPEC-002", depends_on=["SPEC-001"]),
            "SPEC-001": make_spec("SPEC-001"),
        }
        resolver = DependencyResolver(specs)
        order = resolver.topological_sort()
        self.assertEqual(order, ["SPEC-001", "SPEC-002", "SPEC-003"])

    def test_parallel_specs(self):
        specs = {
            "SPEC-A": make_spec("SPEC-A"),
            "SPEC-B": make_spec("SPEC-B"),
        }
        resolver = DependencyResolver(specs)
        order = resolver.topological_sort()
        self.assertEqual(set(order), {"SPEC-A", "SPEC-B"})

    def test_cycle_detection(self):
        specs = {
            "SPEC-001": make_spec("SPEC-001", depends_on=["SPEC-002"]),
            "SPEC-002": make_spec("SPEC-002", depends_on=["SPEC-001"]),
        }
        resolver = DependencyResolver(specs)
        with self.assertRaises(CycleError):
            resolver.topological_sort()

    def test_no_deps(self):
        specs = {"SPEC-001": make_spec("SPEC-001")}
        resolver = DependencyResolver(specs)
        self.assertEqual(resolver.topological_sort(), ["SPEC-001"])


class TestParallelGroups(unittest.TestCase):

    def test_groups(self):
        specs = {
            "SPEC-001": make_spec("SPEC-001", status="ready"),
            "SPEC-002": make_spec("SPEC-002", status="ready", depends_on=["SPEC-001"]),
            "SPEC-003": make_spec("SPEC-003", status="ready"),
        }
        resolver = DependencyResolver(specs)
        groups = resolver.get_parallel_groups()
        self.assertEqual(len(groups), 2)
        self.assertIn("SPEC-001", groups[0])
        self.assertIn("SPEC-003", groups[0])
        self.assertEqual(groups[1], ["SPEC-002"])


class TestRunnableSpecs(unittest.TestCase):

    def test_runnable(self):
        specs = {
            "SPEC-001": make_spec("SPEC-001", status="ready"),
            "SPEC-002": make_spec("SPEC-002", status="ready", depends_on=["SPEC-001"]),
        }
        resolver = DependencyResolver(specs)
        runnable = resolver.get_runnable_specs()
        self.assertIn("SPEC-001", runnable)
        self.assertNotIn("SPEC-002", runnable)


if __name__ == '__main__':
    unittest.main()