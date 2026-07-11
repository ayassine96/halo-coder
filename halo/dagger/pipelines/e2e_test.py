#!/usr/bin/env python3
"""Dagger E2E test pipeline using Playwright (DAG-R4).

Hermetic execution: runs Playwright tests inside a container via Dagger CLI.
Fallback: docker run with Playwright image if Dagger unavailable (REL-4).
"""

import subprocess
import os
import shutil
import logging

from halo.dagger.engine_config import PLAYWRIGHT_IMAGE

_log = logging.getLogger("halo.dagger.e2e")


def _dagger_available():
    return shutil.which("dagger") is not None


def run_e2e_test(repo_path, browser="chromium", extra_args=None):
    """Run Playwright E2E tests hermetically via Dagger or docker fallback (DAG-R4)."""
    extra_args = extra_args or []
    if _dagger_available():
        return _run_via_dagger(repo_path, browser, extra_args)
    _log.warning("Dagger unavailable, using docker fallback for E2E tests (REL-4)")
    return _run_via_docker(repo_path, browser, extra_args)


def _run_via_dagger(repo_path, browser, extra_args):
    """Run Playwright E2E tests in a Dagger container (DAG-R4)."""
    args = " ".join(extra_args) if extra_args else ""

    dagger_script = f'''
import dagger
from dagger import function, object_type

@object_type
class E2eTestPipeline:
    @function
    async def run(self, src: dagger.Directory) -> str:
        container = (
            dagger.container()
            .from_("{PLAYWRIGHT_IMAGE}")
            .with_mounted_directory("/src", src)
            .with_workdir("/src")
            .with_exec(["npm", "ci"], use_entrypoint=False)
            .with_exec(["npx", "playwright", "test", "--project={browser}", "{args}"], use_entrypoint=False)
        )
        try:
            return await container.stdout()
        except dagger.ExecError as e:
            return f"E2E tests failed (exit=" + str(e.exit_code) + ")"
'''

    result = subprocess.run(
        ["dagger", "-m", "python", "run", "e2e-test-pipeline", "run", "--src", repo_path],
        capture_output=True, text=True, timeout=900, cwd=repo_path,
        input=dagger_script,
    )
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "browser": browser,
        "execution_mode": "dagger",
    }


def _run_via_docker(repo_path, browser, extra_args):
    """Fallback: run Playwright in a Docker container (REL-4)."""
    args = " ".join(extra_args) if extra_args else ""
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{repo_path}:/src",
        "-w", "/src",
        PLAYWRIGHT_IMAGE,
        "sh", "-c", f"npm ci && npx playwright test --project={browser} {args}",
    ]

    try:
        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        _log.error("Docker not available, falling back to host subprocess")
        return _run_host_subprocess(repo_path, browser, extra_args)

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "browser": browser,
        "execution_mode": "docker",
    }


def _run_host_subprocess(repo_path, browser, extra_args):
    """Last resort: run on host (NOT hermetic)."""
    _log.warning("Running E2E tests on host (NOT hermetic)")
    cmd = ["npx", "playwright", "test", f"--project={browser}"] + extra_args
    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "browser": browser,
        "execution_mode": "host_subprocess",
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