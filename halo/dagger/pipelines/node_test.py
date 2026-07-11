#!/usr/bin/env python3
"""Dagger Node.js test pipeline (DAG-R2, DAG-R3).

Hermetic execution: runs npm/yarn test inside a Docker container via Dagger CLI.
Fallback: docker run if Dagger unavailable (REL-4).
"""

import subprocess
import os
import shutil
import logging

_log = logging.getLogger("halo.dagger.node")


def _dagger_available():
    return shutil.which("dagger") is not None


def run_node_test(repo_path, runner="npm", extra_args=None):
    """Run Node.js tests hermetically via Dagger or docker fallback (DAG-R2)."""
    extra_args = extra_args or []
    if _dagger_available():
        return _run_via_dagger(repo_path, runner, extra_args)
    _log.warning("Dagger unavailable, using docker fallback for Node tests (REL-4)")
    return _run_via_docker(repo_path, runner, extra_args)


def _run_via_dagger(repo_path, runner, extra_args):
    """Run node tests in a Dagger container (DAG-R2)."""
    install_cmd = "npm ci" if runner == "npm" else "yarn install --frozen-lockfile"
    test_cmd = f"{runner} test"
    args = " ".join(extra_args) if extra_args else ""

    dagger_script = f'''
import dagger
from dagger import function, object_type

@object_type
class NodeTestPipeline:
    @function
    async def run(self, src: dagger.Directory) -> str:
        container = (
            dagger.container()
            .from_("node:20-slim")
            .with_mounted_directory("/src", src)
            .with_workdir("/src")
            .with_exec(["{install_cmd}"], use_entrypoint=False)
            .with_exec(["{test_cmd}", "{args}"], use_entrypoint=False)
        )
        try:
            return await container.stdout()
        except dagger.ExecError as e:
            return f"tests failed (exit=" + str(e.exit_code) + "): " + str(e)
'''

    result = subprocess.run(
        ["dagger", "-m", "python", "run", "node-test-pipeline", "run", "--src", repo_path],
        capture_output=True, text=True, timeout=600, cwd=repo_path,
        input=dagger_script,
    )
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "execution_mode": "dagger",
    }


def _run_via_docker(repo_path, runner, extra_args):
    """Fallback: run node tests in a Docker container (REL-4)."""
    install_cmd = "npm ci" if runner == "npm" else "yarn install --frozen-lockfile"
    test_cmd = f"{runner} test"
    if extra_args:
        test_cmd += " -- " + " ".join(extra_args)

    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{repo_path}:/src",
        "-w", "/src",
        "node:20-slim",
        "sh", "-c", f"{install_cmd} && {test_cmd}",
    ]

    try:
        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        _log.error("Docker not available, falling back to host subprocess")
        return _run_host_subprocess(repo_path, runner, extra_args)

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "execution_mode": "docker",
    }


def _run_host_subprocess(repo_path, runner, extra_args):
    """Last resort: run on host (NOT hermetic)."""
    _log.warning("Running Node tests on host (NOT hermetic)")
    cmd = [runner, "test"]
    if extra_args:
        cmd.extend(["--"] + extra_args)
    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "execution_mode": "host_subprocess",
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