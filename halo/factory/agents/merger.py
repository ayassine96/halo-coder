#!/usr/bin/env python3
"""Merger agent — squash-merge to main, only component with write access (SEC-4)."""

from halo.factory.agents.prompts import MERGER_SYSTEM


class MergerAgent:
    """Merger agent role (WF-SPEC-14, SEC-4).

    The Merger is the ONLY agent with write access to the main branch.
    Uses a dedicated SSH key or GitHub token (SEC-4).
    """

    def __init__(self, git_ops=None, kernel_client=None):
        self.git = git_ops
        self.kernel = kernel_client

    def build_prompt(self, spec, acceptance_criteria=""):
        prompt = f"{MERGER_SYSTEM}\n\n"
        prompt += f"Spec: {spec.id} — {spec.title}\n"
        prompt += f"Acceptance Criteria:\n{acceptance_criteria}\n\n"
        prompt += "Squash-merge branch to main with AC in commit body."
        return prompt

    def execute(self, spec, acceptance_criteria=""):
        """Perform the squash-merge (SEC-4 — only agent with main write access)."""
        if self.git:
            message = self.git.squash_merge_spec(spec.id, acceptance_criteria)
            self.git.delete_spec_branch(spec.id)
            return {"status": "merged", "message": message, "spec_id": spec.id}
        return {"status": "no_git_ops", "spec_id": spec.id}