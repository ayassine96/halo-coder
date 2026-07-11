#!/usr/bin/env python3
"""AST builder — code→test graph using imports and function references (TDAD-R2).

Uses simple regex-based parsing to avoid tree-sitter dependency in tests.
For production, tree-sitter or jedi can be plugged in as optional backends.
"""

import os
import re

_IMPORT_RE = re.compile(r"^(?:from\s+(\S+)\s+)?import\s+(.+)$", re.MULTILINE)
_DEF_RE = re.compile(r"^\s*def\s+(\w+)|^\s*class\s+(\w+)", re.MULTILINE)
_TEST_REF_RE = re.compile(r"(?:from|import)\s+(.+?)(?:\s+import|\s*$)", re.MULTILINE)
_PYTHON_TEST_PATTERN = re.compile(r"test_\w+\.py$")


def find_python_files(repo_path, exclude=None):
    """Find all .py files in a repo, excluding venvs and common dirs."""
    exclude = exclude or {"venv", ".venv", "node_modules", "__pycache__", ".git", "build", "dist"}
    files = []
    for root, dirs, fns in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude]
        for fn in fns:
            if fn.endswith(".py"):
                files.append(os.path.relpath(os.path.join(root, fn), repo_path))
    return sorted(files)


def parse_imports(file_content):
    """Extract import statements from Python file content."""
    imports = []
    for match in _IMPORT_RE.finditer(file_content):
        module = match.group(1) or ""
        names = [n.strip().strip(",") for n in (match.group(2) or "").split(",") if n.strip()]
        if module:
            imports.append(module)
        imports.extend(names)
    return imports


def parse_defs(file_content):
    """Extract function/class definitions from Python file content."""
    defs = []
    for match in _DEF_RE.finditer(file_content):
        d = match.group(1) or match.group(2)
        if d:
            defs.append(d)
    return defs


def is_test_file(file_path):
    """Check if a file path is a test file."""
    return bool(_PYTHON_TEST_PATTERN.search(file_path))


def build_graph(repo_path, graph_store):
    """Scan a repo and populate the graph store with code→test mappings."""
    files = find_python_files(repo_path)
    test_files = [f for f in files if is_test_file(f)]

    for f in files:
        full_path = os.path.join(repo_path, f)
        try:
            with open(full_path, "r") as fh:
                content = fh.read()
        except (IOError, UnicodeDecodeError):
            continue

        imports = parse_imports(content)
        defs = parse_defs(content)

        if is_test_file(f):
            targets = [imp for imp in imports if not imp.startswith("pytest") and not imp.startswith("unittest")]
            graph_store.add_test(f, targets=targets, fixtures=[])
        else:
            graph_store.add_module(f, imports=imports, defs=defs)

    for test_f in test_files:
        test_data = graph_store._tests.get(test_f, {})
        test_targets = set(test_data.get("targets", []))
        for mod_path, mod_data in graph_store._modules.items():
            mod_name = mod_path.replace("/", ".").replace(".py", "")
            for target in test_targets:
                if target in mod_name or any(target in f"{mod_name}.{d}" for d in mod_data.get("defs", [])):
                    graph_store.add_edge(mod_path, test_f)


def analyze_changed_files(repo_path, changed_files, graph_store):
    """For a set of changed files, return affected tests and confidence."""
    affected = graph_store.get_affected_tests(changed_files)
    uncovered = graph_store.get_uncovered_paths(changed_files)
    if changed_files:
        coverage = 1.0 - (len(uncovered) / len(changed_files))
    else:
        coverage = 0.0
    confidence = min(1.0, coverage + (len(affected) / max(1, len(changed_files) * 3)))
    return affected, confidence, uncovered