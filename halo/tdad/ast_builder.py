#!/usr/bin/env python3
"""AST builder — code→test graph using tree-sitter for Python/JS/TS (TDAD-R2).

Primary: tree-sitter for accurate AST-level parsing (Python, JS, TS).
Fallback: regex-based parsing if tree-sitter is not installed.
"""

import os
import re

_TREE_SITTER_AVAILABLE = False
try:
    import tree_sitter
    import tree_sitter_python
    import tree_sitter_javascript
    import tree_sitter_typescript
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    pass

_IMPORT_RE = re.compile(r"^(?:from\s+(\S+)\s+)?import\s+(.+)$", re.MULTILINE)
_DEF_RE = re.compile(r"^\s*def\s+(\w+)|^\s*class\s+(\w+)", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"""(?:import\s+.*?\s+from\s+['"](.+)['"])|(?:import\s+['"](.+)['"])|(?:require\(['"](.+)['"]\))""", re.MULTILINE)
_JS_DEF_RE = re.compile(r"""\b(?:function|class|const|let|var)\s+(\w+)""", re.MULTILINE)
_PYTHON_TEST_PATTERN = re.compile(r"test_\w+\.py$")
_JS_TEST_PATTERN = re.compile(r"(?:\.test\.|\.spec\.|__tests__/)")

_TEST_PATTERNS = {
    "python": _PYTHON_TEST_PATTERN,
    "javascript": _JS_TEST_PATTERN,
    "typescript": _JS_TEST_PATTERN,
}

_PARSERS = {}
if _TREE_SITTER_AVAILABLE:
    try:
        _PARSERS["python"] = tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))
    except Exception:
        pass
    try:
        _PARSERS["javascript"] = tree_sitter.Parser(tree_sitter.Language(tree_sitter_javascript.language()))
    except Exception:
        pass
    try:
        _PARSERS["typescript"] = tree_sitter.Parser(tree_sitter.Language(tree_sitter_typescript.language_typescript()))
    except Exception:
        pass


def _get_language(file_path):
    """Determine language from file extension."""
    if file_path.endswith(".py"):
        return "python"
    elif file_path.endswith(".js") or file_path.endswith(".jsx"):
        return "javascript"
    elif file_path.endswith(".ts") or file_path.endswith(".tsx"):
        return "typescript"
    return None


def find_source_files(repo_path, exclude=None):
    """Find all source files (.py, .js, .ts) in a repo."""
    exclude = exclude or {"venv", ".venv", "node_modules", "__pycache__", ".git", "build", "dist"}
    files = []
    for root, dirs, fns in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude]
        for fn in fns:
            if fn.endswith((".py", ".js", ".ts", ".jsx", ".tsx")):
                files.append(os.path.relpath(os.path.join(root, fn), repo_path))
    return sorted(files)


def find_python_files(repo_path, exclude=None):
    """Find all .py files (backward compat)."""
    return [f for f in find_source_files(repo_path, exclude) if f.endswith(".py")]


def _tree_sitter_parse(content_bytes, language):
    """Parse code with tree-sitter and extract imports + definitions."""
    if language not in _PARSERS:
        return [], []
    parser = _PARSERS[language]
    tree = parser.parse(content_bytes)
    imports = []
    defs = []

    def walk(node):
        if language == "python":
            if node.type == "import_statement":
                for child in node.children:
                    if child.type in ("dotted_name", "identifier"):
                        imports.append(child.text.decode())
                        break
            elif node.type == "import_from_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        imports.append(child.text.decode())
                        break
            elif node.type in ("function_definition", "class_definition"):
                for child in node.children:
                    if child.type == "identifier":
                        defs.append(child.text.decode())
                        break
        else:
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "string":
                        text = child.text.decode().strip("'\"")
                        imports.append(text)
                        break
            elif node.type in ("function_declaration", "class_declaration"):
                for child in node.children:
                    if child.type == "identifier":
                        defs.append(child.text.decode())
                        break
            elif node.type == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        for vc in child.children:
                            if vc.type == "identifier":
                                defs.append(vc.text.decode())
                                break
                        break
            elif node.type == "export_statement":
                for child in node.children:
                    if child.type == "lexical_declaration":
                        for lc in child.children:
                            if lc.type == "variable_declarator":
                                for vc in lc.children:
                                    if vc.type == "identifier":
                                        defs.append(vc.text.decode())
                                        break
                                break
                    elif child.type == "function_declaration":
                        for fc in child.children:
                            if fc.type == "identifier":
                                defs.append(fc.text.decode())
                                break
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return imports, defs


def _regex_parse_imports(content, language="python"):
    """Fallback regex-based import parsing."""
    if language == "python":
        imports = []
        for match in _IMPORT_RE.finditer(content):
            module = match.group(1) or ""
            names = [n.strip().strip(",") for n in (match.group(2) or "").split(",") if n.strip()]
            if module:
                imports.append(module)
            imports.extend(names)
        return imports
    else:
        imports = []
        for match in _JS_IMPORT_RE.finditer(content):
            for g in match.groups():
                if g:
                    imports.append(g)
                    break
        return imports


def _regex_parse_defs(content, language="python"):
    """Fallback regex-based definition parsing."""
    if language == "python":
        defs = []
        for match in _DEF_RE.finditer(content):
            d = match.group(1) or match.group(2)
            if d:
                defs.append(d)
        return defs
    else:
        defs = []
        for match in _JS_DEF_RE.finditer(content):
            d = match.group(1)
            if d:
                defs.append(d)
        return defs


def parse_imports(content, language="python"):
    """Extract import statements from source content."""
    if _TREE_SITTER_AVAILABLE and language in _PARSERS:
        try:
            imports, _ = _tree_sitter_parse(content.encode(), language)
            return imports
        except Exception:
            pass
    return _regex_parse_imports(content, language)


def parse_defs(content, language="python"):
    """Extract function/class definitions from source content."""
    if _TREE_SITTER_AVAILABLE and language in _PARSERS:
        try:
            _, defs = _tree_sitter_parse(content.encode(), language)
            return defs
        except Exception:
            pass
    return _regex_parse_defs(content, language)


def is_test_file(file_path):
    """Check if a file path is a test file."""
    for lang, pattern in _TEST_PATTERNS.items():
        if pattern.search(file_path):
            return True
    return False


def build_graph(repo_path, graph_store):
    """Scan a repo and populate the graph store with code→test mappings."""
    files = find_source_files(repo_path)
    test_files = [f for f in files if is_test_file(f)]

    for f in files:
        full_path = os.path.join(repo_path, f)
        try:
            with open(full_path, "r") as fh:
                content = fh.read()
        except (IOError, UnicodeDecodeError):
            continue

        language = _get_language(f) or "python"
        imports = parse_imports(content, language)
        defs = parse_defs(content, language)

        if is_test_file(f):
            targets = [imp for imp in imports
                       if not imp.startswith("pytest")
                       and not imp.startswith("unittest")
                       and not imp.startswith("node:")
                       and not imp.startswith("vitest")]
            graph_store.add_test(f, targets=targets, fixtures=[])
        else:
            graph_store.add_module(f, imports=imports, defs=defs)

    for test_f in test_files:
        test_data = graph_store._tests.get(test_f, {})
        test_targets = set(test_data.get("targets", []))
        for mod_path, mod_data in graph_store._modules.items():
            mod_name = mod_path.replace("/", ".").replace(".py", "").replace(".ts", "").replace(".js", "")
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