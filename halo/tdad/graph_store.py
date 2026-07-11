#!/usr/bin/env python3
"""Graph store for code→test dependency mappings (TDAD-R2, TDAD-NF4).

Persists the graph as JSON on disk, reloadable on restart.
"""

import json
import os
from collections import defaultdict


class GraphStore:
    """Persistent code→test dependency graph."""

    def __init__(self, index_path=None):
        self.index_path = index_path or "/tmp/halo-tdad-graph.json"
        self._modules = {}  # file path → {imports: [], defs: []}
        self._tests = {}    # test file path → {targets: [], fixtures: []}
        self._edges = {}     # source_file → [test_file paths]

    def load(self):
        """Load graph from disk."""
        if os.path.exists(self.index_path):
            with open(self.index_path, "r") as f:
                data = json.load(f)
            self._modules = data.get("modules", {})
            self._tests = data.get("tests", {})
            self._edges = data.get("edges", {})

    def save(self):
        """Persist graph to disk."""
        data = {"modules": self._modules, "tests": self._tests, "edges": self._edges}
        os.makedirs(os.path.dirname(self.index_path) or ".", exist_ok=True)
        with open(self.index_path, "w") as f:
            json.dump(data, f, indent=2)

    def add_module(self, file_path, imports=None, defs=None):
        """Add/update a source module."""
        self._modules[file_path] = {
            "imports": imports or [],
            "defs": defs or [],
        }

    def add_test(self, file_path, targets=None, fixtures=None):
        """Add/update a test file."""
        self._tests[file_path] = {
            "targets": targets or [],
            "fixtures": fixtures or [],
        }

    def add_edge(self, source_file, test_file):
        """Map source file → test file."""
        if source_file not in self._edges:
            self._edges[source_file] = []
        if test_file not in self._edges[source_file]:
            self._edges[source_file].append(test_file)

    def get_affected_tests(self, changed_files):
        """Return list of test file paths affected by changes to changed_files."""
        affected = set()
        for f in changed_files:
            if f in self._edges:
                affected.update(self._edges[f])
            for mod_path, mod in self._modules.items():
                if f in mod.get("imports", []):
                    if mod_path in self._edges:
                        affected.update(self._edges[mod_path])
        return sorted(affected)

    def get_uncovered_paths(self, changed_files):
        """Return source files with no associated tests."""
        uncovered = []
        for f in changed_files:
            if f not in self._edges or not self._edges[f]:
                uncovered.append(f)
        return uncovered

    def clear(self):
        self._modules = {}
        self._tests = {}
        self._edges = {}

    @property
    def module_count(self):
        return len(self._modules)

    @property
    def test_count(self):
        return len(self._tests)

    @property
    def edge_count(self):
        return sum(len(v) for v in self._edges.values())