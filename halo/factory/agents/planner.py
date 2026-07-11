#!/usr/bin/env python3
"""Planner agent — reads spec + ARCH.md + RAG, writes plan.md (SRS §4.2.2)."""

from halo.factory.agents.prompts import PLANNER_SYSTEM


class PlannerAgent:
    """Planner agent role (WF-SPEC-5)."""

    def __init__(self, kernel_client=None, arch_manager=None, rag_query=None):
        self.kernel = kernel_client
        self.arch = arch_manager
        self.rag = rag_query

    def build_prompt(self, spec):
        """Build the planner prompt with RAG context (MEM-R4)."""
        prompt = f"{PLANNER_SYSTEM}\n\n"
        prompt += f"Spec ID: {spec.id}\nTitle: {spec.title}\n"
        prompt += f"Body:\n{spec.body}\n\n"
        if self.arch and self.arch.exists():
            prompt += f"Architecture Context:\n{self.arch.read()[:2000]}\n\n"
        if self.rag:
            rag_ctx = self.rag.retrieve_context(spec)
            if rag_ctx:
                prompt += f"{rag_ctx}\n\n"
        prompt += "Create a plan.md with implementation approach, file changes, and test strategy."
        return prompt

    def execute(self, spec):
        """Execute the planner agent."""
        prompt = self.build_prompt(spec)
        if self.kernel:
            return self.kernel.chat(prompt, model="halo-reasoning")
        return prompt