#!/usr/bin/env python3
"""Dagger E2E test pipeline using Playwright (DAG-R4)."""

import subprocess
import os
from halo.dagger.engine_config import PLAYWRIGHT_IMAGE


def run_e2e_test(repo_path, browser="chromium", extra_args=None):
    """Run Playwright E2E tests. Returns dict with results."""
    extra_args = extra_args or []
    cmd = ["npx", "playwright", "test", f"--project={browser}"] + extra_args
    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
        "browser": browser,
    }


def build_dagger_e2e_pipeline(repo_path, browser="chromium"):
    """Build a Dagger E2E pipeline spec with Playwright container (DAG-R4)."""
    return {
        "pipeline": "e2e-playwright",
        "repo_path": repo_path,
        "mount": {"source": repo_path, "target": "/src", "read_only": True},
        "container_image": PLAYWRIGHT_IMAGE,
        "steps": [
            {"name": "install", "cmd": "npm ci", "cache_key": "deps:e2e"},
            {"name": "playwright", "cmd": f"npx playwright test --project={browser}", "cache_key": "tests:e2e"},
        ],
        "artifacts": {"report": "playwright-report/"},
    }