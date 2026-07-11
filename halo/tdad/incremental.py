#!/usr/bin/env python3
"""Incremental index updates (TDAD-R4).

Updates the graph when new test/source files are added without full reindexing.
"""

import os
from halo.tdad.ast_builder import parse_imports, parse_defs, is_test_file, build_graph


def incremental_update(repo_path, changed_files, graph_store):
    """Update the graph for only the changed files (TDAD-R4).

    Called when new files are added or existing files are modified.
    Removes stale edges for changed source files and re-adds them.
    """
    for f in changed_files:
        full_path = os.path.join(repo_path, f)

        if f in graph_store._edges:
            del graph_store._edges[f]

        try:
            with open(full_path, "r") as fh:
                content = fh.read()
        except (IOError, UnicodeDecodeError, FileNotFoundError):
            continue

        imports = parse_imports(content)
        defs = parse_defs(content)

        if is_test_file(f):
            targets = [imp for imp in imports if not imp.startswith("pytest") and not imp.startswith("unittest")]
            graph_store.add_test(f, targets=targets, fixtures=[])
        else:
            graph_store.add_module(f, imports=imports, defs=defs)

    for test_f, test_data in graph_store._tests.items():
        test_targets = set(test_data.get("targets", []))
        for mod_path, mod_data in graph_store._modules.items():
            mod_name = mod_path.replace("/", ".").replace(".py", "")
            for target in test_targets:
                if target in mod_name or any(target in f"{mod_name}.{d}" for d in mod_data.get("defs", [])):
                    graph_store.add_edge(mod_path, test_f)


def full_reindex(repo_path, graph_store):
    """Full reindex of a repository (TDAD-NF1)."""
    graph_store.clear()
    build_graph(repo_path, graph_store)
    return graph_store.module_count, graph_store.test_count