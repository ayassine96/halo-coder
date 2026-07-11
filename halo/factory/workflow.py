#!/usr/bin/env python3
"""Spec-driven workflow orchestration (WF-SPEC-1 through WF-SPEC-15).

Full pipeline: human writes spec → ready → planner → coder (TDD) → tester → reviewer → approval → merger → merged.
Includes TDD loop (Red → Green → Refactor), failure retry (max 3), TDAD/RAG injection.
"""

from halo.common.models import (
    SPEC_STATUS_DRAFT, SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS,
    SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED,
    SPEC_STATUS_FAILED_RED, SPEC_STATUS_FAILED_GREEN, SPEC_STATUS_FAILED_E2E,
)
from halo.specs.state_machine import transition as do_transition


MAX_RETRIES = 3


class Workflow:
    """Orchestrate the full spec-driven development workflow (WF-SPEC-1..15)."""

    def __init__(self, dispatcher=None, devpod_manager=None, event_publisher=None,
                 circuit_breaker=None, k3s_client=None, kernel_client=None,
                 tdad_client=None, dag_client=None, git_ops=None, arch_manager=None,
                 rag_query=None, log=None):
        self.dispatcher = dispatcher
        self.devpod_manager = devpod_manager
        self.event_publisher = event_publisher
        self.circuit_breaker = circuit_breaker
        self.k3s = k3s_client
        self.kernel = kernel_client
        self.tdad = tdad_client
        self.dag = dag_client
        self.git_ops = git_ops
        self.arch_manager = arch_manager
        self.rag = rag_query
        self.log = log
        self._retry_counts = {}

    def start_spec(self, spec_id, spec):
        """Start the workflow for a ready spec (WF-SPEC-3..5)."""
        if self.devpod_manager:
            self.devpod_manager.scale_up(spec_id)
        if self.dispatcher:
            rag_context = ""
            if self.rag:
                rag_context = self.rag.retrieve_context(spec)
            self.dispatcher.dispatch_planner(spec_id, prompt=self._planner_prompt(spec, rag_context))
        if self.event_publisher:
            self.event_publisher.log_event(spec_id, f"Workflow started for {spec_id}")

    def _planner_prompt(self, spec, rag_context=""):
        """Build planner system prompt (WF-SPEC-5)."""
        prompt = f"You are the Planner agent. Read spec {spec.id}: {spec.title}\n"
        prompt += f"Acceptance criteria:\n{spec.body}\n"
        if self.arch_manager and self.arch_manager.exists():
            prompt += f"\nArchitecture context:\n{self.arch_manager.read()[:2000]}\n"
        if rag_context:
            prompt += f"\nRAG context:\n{rag_context}\n"
        prompt += "\nCreate a plan.md file with implementation approach."
        return prompt

    def on_plan_complete(self, spec_id, spec):
        """Called when plan.md is committed (WF-SPEC-6..7)."""
        tdad_tests = []
        if self.tdad:
            try:
                result = self.tdad.analyze(spec_id=spec_id)
                tdad_tests = result.get("affected_tests", [])
            except Exception:
                pass
        if self.dispatcher:
            self.dispatcher.dispatch_coder(spec_id, tdad_tests=tdad_tests)
        if self.event_publisher:
            self.event_publisher.log_event(spec_id, f"Plan complete, dispatching coder with {len(tdad_tests)} TDAD tests")

    def on_code_committed(self, spec_id, spec):
        """Called when code is committed (WF-SPEC-8..9)."""
        if self.dispatcher:
            self.dispatcher.dispatch_tester(spec_id)
        if self.event_publisher:
            self.event_publisher.log_event(spec_id, "Code committed, dispatching tester")

    def on_test_complete(self, spec_id, spec, passed, failure_type=""):
        """Called when tests complete (WF-SPEC-10..11)."""
        if passed:
            if self.dispatcher:
                self.dispatcher.dispatch_reviewer(spec_id)
            if self.event_publisher:
                self.event_publisher.log_event(spec_id, "Tests passed, dispatching reviewer")
        else:
            retries = self._retry_counts.get(spec_id, 0)
            if retries < MAX_RETRIES:
                self._retry_counts[spec_id] = retries + 1
                if self.dispatcher:
                    self.dispatcher.dispatch_coder(spec_id, prompt=f"Tests failed ({failure_type}). Fix and retry. Attempt {retries + 1}/{MAX_RETRIES}")
                if self.event_publisher:
                    self.event_publisher.log_event(spec_id, f"Tests failed ({failure_type}), retry {retries + 1}/{MAX_RETRIES}")
            else:
                if self.event_publisher:
                    self.event_publisher.alert(spec_id, f"Max retries exceeded ({MAX_RETRIES}) — marking as failed ({failure_type})")

    def on_review_complete(self, spec_id, spec, approved):
        """Called when review is done (WF-SPEC-12)."""
        if approved:
            if self.event_publisher:
                self.event_publisher.request_approval(spec_id, f"Spec {spec_id} implemented, awaiting human approval")
        else:
            if self.event_publisher:
                self.event_publisher.alert(spec_id, f"Review failed for {spec_id}")

    def on_human_approved(self, spec_id, spec, acceptance_criteria=""):
        """Called when human approves (WF-SPEC-13..14)."""
        if self.dispatcher:
            self.dispatcher.dispatch_merger(spec_id, prompt="Squash-merge to main")
        if self.git_ops:
            self.git_ops.squash_merge_spec(spec_id, acceptance_criteria)
            self.git_ops.delete_spec_branch(spec_id)
        if self.event_publisher:
            self.event_publisher.log_event(spec_id, f"Spec {spec_id} merged to main")
            self.event_publisher.metric(spec_id, "merged:1")

    def on_human_rejected(self, spec_id, spec, reason=""):
        """Called when human rejects (back to draft)."""
        if self.event_publisher:
            self.event_publisher.log_event(spec_id, f"Spec {spec_id} rejected: {reason}")
        self._retry_counts.pop(spec_id, None)

    def on_devpod_complete(self, spec_id):
        """Called when DevPod task is done — schedule cleanup (DP-R9)."""
        if self.devpod_manager:
            import threading
            def cleanup():
                import time
                time.sleep(300)
                self.devpod_manager.destroy(spec_id)
            threading.Thread(target=cleanup, daemon=True).start()


# TDD loop states (WF-TDD-1..5)
TDD_RED = "red"
TDD_GREEN = "green"
TDD_REFACTOR = "refactor"


class TDDLoop:
    """Manage the TDD Red→Green→Refactor cycle (WF-TDD-1..5)."""

    def __init__(self):
        self._phases = {}

    def start(self, spec_id):
        """Start TDD loop for a spec (WF-TDD-1: write failing tests first)."""
        self._phases[spec_id] = TDD_RED

    def verify_red(self, spec_id, tests_failed):
        """Verify tests fail before implementation (WF-TDD-2)."""
        if tests_failed:
            self._phases[spec_id] = TDD_GREEN
            return True
        return False

    def verify_green(self, spec_id, tests_passed):
        """Verify tests pass after implementation (WF-TDD-3)."""
        if tests_passed:
            self._phases[spec_id] = TDD_REFACTOR
            return True
        return False

    def complete_refactor(self, spec_id, tests_still_pass):
        """Complete refactor phase (WF-TDD-4)."""
        if tests_still_pass:
            self._phases.pop(spec_id, None)
            return True
        return False

    def get_phase(self, spec_id):
        return self._phases.get(spec_id, None)