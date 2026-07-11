#!/usr/bin/env python3
"""Coder agent — implements plan with TDD and TDAD injection (SRS §4.2.2, TDAD-R6)."""

from halo.factory.agents.prompts import CODER_SYSTEM, format_tdad_injection


class CoderAgent:
    """Coder agent role (WF-SPEC-7..8, WF-TDD-1..5)."""

    def __init__(self, kernel_client=None, tdad_client=None):
        self.kernel = kernel_client
        self.tdad = tdad_client

    def build_prompt(self, spec, plan, changed_files=None, tdad_tests=None, failure_logs=""):
        """Build the coder prompt with TDAD injection (TDAD-R6)."""
        prompt = f"{CODER_SYSTEM}\n\n"
        prompt += f"Spec: {spec.id} — {spec.title}\n"
        prompt += f"Plan:\n{plan}\n\n"
        if changed_files and tdad_tests:
            prompt += format_tdad_injection(changed_files, tdad_tests) + "\n\n"
        if failure_logs:
            prompt += f"Previous test failures:\n{failure_logs}\n\n"
        prompt += "Follow TDD: write failing tests first (Red), implement to pass (Green), then refactor."
        return prompt

    def execute(self, spec, plan, changed_files=None, failure_logs=""):
        """Execute the coder agent."""
        tdad_tests = []
        if self.tdad and changed_files:
            try:
                result = self.tdad.analyze(spec_id=spec.id)
                tdad_tests = result.get("affected_tests", [])
            except Exception:
                pass
        prompt = self.build_prompt(spec, plan, changed_files, tdad_tests, failure_logs)
        if self.kernel:
            return self.kernel.chat(prompt, model="halo-reasoning")
        return prompt