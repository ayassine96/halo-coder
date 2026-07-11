#!/usr/bin/env python3
"""Dagger Node.js test pipeline (DAG-R3)."""

import subprocess
import os
import tempfile


def run_node_test(repo_path, runner="npm", extra_args=None):
    """Run Node.js tests via Dagger. Returns dict with results."""
    extra_args = extra_args or []
    if runner == "yarn":
        cmd = ["yarn", "test"] + extra_args
    else:
        cmd = ["npm", "test", "--"] + extra_args
    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
    }


def build_dagger_node_pipeline(repo_path, junit_output="junit.xml", runner="npm"):
    """Build a Dagger pipeline spec dict for Node.js test execution."""
    install_cmd = "npm ci" if runner == "npm" else "yarn install --frozen-lockfile"
    test_cmd = f"{runner} test"
    return {
        "pipeline": "node-test",
        "repo_path": repo_path,
        "mount": {"source": repo_path, "target": "/src", "read_only": True},
        "steps": [
            {"name": "install", "cmd": install_cmd, "cache_key": "deps:node"},
            {"name": "test", "cmd": test_cmd, "cache_key": "tests:node"},
        ],
        "artifacts": {"junit": junit_output},
    }