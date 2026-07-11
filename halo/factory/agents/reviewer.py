#!/usr/bin/env python3
"""Reviewer agent — reviews git diff against spec AC (SRS §4.2.2)."""

from halo.factory.agents.prompts import REVIEWER_SYSTEM


class ReviewerAgent:
    """Reviewer agent role (WF-SPEC-11)."""

    def __init__(self, kernel_client=None):
        self.kernel = kernel_client

    def build_prompt(self, spec, git_diff=""):
        """Build the reviewer prompt."""
        prompt = f"{REVIEWER_SYSTEM}\n\n"
        prompt += f"Spec: {spec.id} — {spec.title}\n"
        prompt += f"Acceptance Criteria:\n{spec.body}\n\n"
        prompt += f"Git Diff:\n{git_diff[:5000]}\n\n"
        prompt += "Assess quality, completeness, and adherence to acceptance criteria.\n"
        prompt += "Output: review comment + approve/reject recommendation."
        return prompt

    def execute(self, spec, git_diff=""):
        prompt = self.build_prompt(spec, git_diff)
        if self.kernel:
            return self.kernel.chat(prompt, model="halo-reasoning")
        return prompt