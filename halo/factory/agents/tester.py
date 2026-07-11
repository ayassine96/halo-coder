#!/usr/bin/env python3
"""Tester agent — runs Dagger test pipelines (SRS §4.2.2)."""

from halo.factory.agents.prompts import TESTER_SYSTEM
from halo.dagger.pipelines import python_test, node_test, e2e_test


class TesterAgent:
    """Tester agent role (WF-SPEC-9)."""

    def __init__(self, kernel_client=None, dagger_engine=None):
        self.kernel = kernel_client
        self.dagger = dagger_engine

    def run_tests(self, repo_path, language="python", extra_args=None):
        """Run tests via Dagger pipeline (DAG-R2)."""
        if language == "python":
            return python_test.run_python_test(repo_path, extra_args)
        elif language == "node":
            return node_test.run_node_test(repo_path, extra_args=extra_args)
        elif language == "e2e":
            return e2e_test.run_e2e_test(repo_path, extra_args=extra_args)
        return {"error": f"Unknown language: {language}"}

    def build_prompt(self, spec, test_results=None):
        prompt = f"{TESTER_SYSTEM}\n\nSpec: {spec.id}\n"
        if test_results:
            prompt += f"Test results:\n{test_results}\n"
        return prompt

    def execute(self, spec, repo_path, language="python"):
        results = self.run_tests(repo_path, language)
        return results