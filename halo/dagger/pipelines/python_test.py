#!/usr/bin/env python3
"""Dagger Python test pipeline (DAG-R2, DAG-R3).

Hermetic execution: runs pytest inside a Docker container via Dagger CLI.
Fallback: docker run if Dagger unavailable (REL-4).
Returns structured results: exit code, stdout, stderr, JUnit XML.
"""

import subprocess
import os
import tempfile
import shutil
import logging

_log = logging.getLogger("halo.dagger.python")


def _dagger_available():
    """Check if Dagger CLI is available."""
    return shutil.which("dagger") is not None


def run_python_test(repo_path, extra_args=None):
    """Run Python tests hermetically via Dagger or docker fallback (DAG-R2).

    Returns dict with: exit_code, stdout, stderr, junit_xml, lint results.
    """
    extra_args = extra_args or []
    if _dagger_available():
        return _run_via_dagger(repo_path, extra_args)
    _log.warning("Dagger unavailable, using docker fallback for hermetic tests (REL-4)")
    return _run_via_docker(repo_path, extra_args)


def _run_via_dagger(repo_path, extra_args):
    """Run pytest in a Dagger container (DAG-R2, DAG-R3)."""
    junit_file = "halo-junit.xml"
    pytest_args = " ".join(extra_args) if extra_args else ""

    dagger_script = f'''
import dagger
from dagger import function, object_type

@object_type
class PythonTestPipeline:
    @function
    async def run(self, src: dagger.Directory) -> str:
        container = (
            dagger.container()
            .from_("python:3.12-slim")
            .with_mounted_directory("/src", src)
            .with_mounted_temp("/tmp")
            .with_workdir("/src")
        )
        has_reqs = await container.file("requirements.txt").exists() if False else True
        container = (
            container
            .with_exec(["pip", "install", "pytest", "pytest-cov"], use_entrypoint=False)
        )
        try:
            test_exit = await container.with_exec(["pytest", "--junitxml={junit_file}", "-v", "{pytest_args}"]).sync()
            exit_code = 0
        except dagger.ExecError as e:
            exit_code = e.exit_code or 1
        stdout = await container.stdout()
        return stdout or "Dagger: tests completed (exit=" + str(exit_code) + ")"
'''

    result = subprocess.run(
        ["dagger", "-m", "python", "run", "python-test-pipeline", "run", "--src", repo_path],
        capture_output=True, text=True, timeout=600, cwd=repo_path,
        input=dagger_script,
    )
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "junit_xml": "",
        "execution_mode": "dagger",
    }


def _run_via_docker(repo_path, extra_args):
    """Fallback: run pytest in a Docker container (REL-4)."""
    junit_path = "/tmp/halo-junit.xml"
    pytest_cmd = ["pytest", f"--junitxml={junit_path}"] + extra_args

    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{repo_path}:/src:ro",
        "-v", f"{tempfile.gettempdir()}/halo-junit.xml:{junit_path}",
        "-w", "/src",
        "python:3.12-slim",
    ] + ["sh", "-c", "pip install pytest pytest-cov && " + " ".join(pytest_cmd)]

    try:
        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        _log.error("Docker not available either, falling back to host subprocess")
        return _run_host_subprocess(repo_path, extra_args)

    junit_xml = ""
    junit_file = os.path.join(tempfile.gettempdir(), "halo-junit.xml")
    if os.path.exists(junit_file):
        with open(junit_file, "r") as f:
            junit_xml = f.read()

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "junit_xml": junit_xml,
        "execution_mode": "docker",
    }


def _run_host_subprocess(repo_path, extra_args):
    """Last resort: run pytest directly on host (not hermetic, logged as warning)."""
    _log.warning("Running tests on host (NOT hermetic) — neither Dagger nor Docker available")
    junit_path = os.path.join(tempfile.gettempdir(), "halo-junit.xml")
    pytest_cmd = ["pytest", f"--junitxml={junit_path}"] + extra_args
    result = subprocess.run(pytest_cmd, cwd=repo_path, capture_output=True, text=True)
    junit_xml = ""
    if os.path.exists(junit_path):
        with open(junit_path, "r") as f:
            junit_xml = f.read()
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "junit_xml": junit_xml,
        "execution_mode": "host_subprocess",
    }


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