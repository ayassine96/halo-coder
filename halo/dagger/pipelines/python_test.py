#!/usr/bin/env python3
"""Dagger Python test pipeline (DAG-R3).

1. Mount source code read-only
2. Install dependencies from requirements.txt or pyproject.toml
3. Run pytest with --junitxml output
4. Run ruff check or mypy if configured
5. Return structured results (exit code, stdout, stderr, XML artifact)
"""

import subprocess
import os
import tempfile


def run_python_test(repo_path, extra_args=None):
    """Run Python tests via Dagger. Returns dict with results."""
    extra_args = extra_args or []
    results = {"junit_xml": "", "stdout": "", "stderr": "", "exit_code": 1, "lint_stdout": "", "lint_exit_code": 0}

    junit_path = os.path.join(tempfile.gettempdir(), "halo-junit.xml")
    pytest_cmd = ["pytest", "--junitxml=" + junit_path] + extra_args
    pytest_result = subprocess.run(pytest_cmd, cwd=repo_path, capture_output=True, text=True)
    results["stdout"] = pytest_result.stdout
    results["stderr"] = pytest_result.stderr
    results["exit_code"] = pytest_result.returncode
    if os.path.exists(junit_path):
        with open(junit_path, "r") as f:
            results["junit_xml"] = f.read()

    for tool in ("ruff", "mypy"):
        if os.path.exists(os.path.join(repo_path, "pyproject.toml")) or os.path.exists(os.path.join(repo_path, "setup.cfg")):
            lint_cmd = [tool, "check", "."]
            lint_result = subprocess.run(lint_cmd, cwd=repo_path, capture_output=True, text=True)
            results[f"{tool}_stdout"] = lint_result.stdout + lint_result.stderr
            results[f"{tool}_exit_code"] = lint_result.returncode

    return results


def build_dagger_python_pipeline(repo_path, junit_output="junit.xml", run_ruff=True, run_mypy=False):
    """Build a Dagger pipeline spec dict for remote execution."""
    spec = {
        "pipeline": "python-test",
        "repo_path": repo_path,
        "mount": {"source": repo_path, "target": "/src", "read_only": True},
        "steps": [
            {"name": "install", "cmd": "pip install -e .", "cache_key": "deps:py"},
            {"name": "pytest", "cmd": f"pytest --junitxml={junit_output}", "cache_key": "tests:py"},
        ],
        "artifacts": {"junit": junit_output},
    }
    if run_ruff:
        spec["steps"].append({"name": "ruff", "cmd": "ruff check ."})
    if run_mypy:
        spec["steps"].append({"name": "mypy", "cmd": "mypy ."})
    return spec