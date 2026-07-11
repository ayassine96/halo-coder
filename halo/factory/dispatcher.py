#!/usr/bin/env python3
"""Redis Streams dispatcher — work queue + agent role dispatch (OR-R5, OR-R2 §4.2.2).

Agent roles: Planner, Coder, Tester, Reviewer, Merger (SRS §4.2.2 table).
"""

import json
from halo.common.models import AgentTask, STREAM_QUEUE


ROLE_PLANNER = "planner"
ROLE_CODER = "coder"
ROLE_TESTER = "tester"
ROLE_REVIEWER = "reviewer"
ROLE_MERGER = "merger"

ROLE_MODEL_MAP = {
    ROLE_PLANNER: "halo-reasoning",
    ROLE_CODER: "halo-reasoning",
    ROLE_TESTER: "halo-fast",
    ROLE_REVIEWER: "halo-reasoning",
    ROLE_MERGER: "halo-fast",
}

ROLE_TOOLS = {
    ROLE_PLANNER: ["read_spec", "read_arch", "read_tdad"],
    ROLE_CODER: ["opencode", "tdad_query", "dagger_test"],
    ROLE_TESTER: ["dagger_pipeline", "pytest"],
    ROLE_REVIEWER: ["git_diff", "read_spec"],
    ROLE_MERGER: ["git_merge", "git_tag"],
}


class Dispatcher:
    """Dispatch agent tasks via Redis Streams (OR-R5)."""

    def __init__(self, redis_client=None):
        self.redis = redis_client

    def dispatch(self, spec_id, role, prompt="", branch="", tools=None):
        """Enqueue an agent task to Redis Streams."""
        task = AgentTask(
            spec_id=spec_id,
            role=role,
            model_profile=ROLE_MODEL_MAP.get(role, "halo-reasoning"),
            prompt=prompt,
            tools=tools or ROLE_TOOLS.get(role, []),
            branch=branch or f"agent/{spec_id}",
        )
        if self.redis:
            self.redis.stream_enqueue(STREAM_QUEUE, {
                "spec_id": spec_id,
                "role": role,
                "model": task.model_profile,
                "prompt": prompt,
                "branch": task.branch,
                "tools": json.dumps(task.tools),
            })
        return task

    def dispatch_planner(self, spec_id, prompt=""):
        return self.dispatch(spec_id, ROLE_PLANNER, prompt=prompt)

    def dispatch_coder(self, spec_id, prompt="", tdad_tests=None):
        if tdad_tests:
            prompt += f"\n\nAffected tests: {', '.join(tdad_tests)}\nYou MUST run these tests after your changes and ensure they pass."
        return self.dispatch(spec_id, ROLE_CODER, prompt=prompt)

    def dispatch_tester(self, spec_id, prompt=""):
        return self.dispatch(spec_id, ROLE_TESTER, prompt=prompt)

    def dispatch_reviewer(self, spec_id, prompt=""):
        return self.dispatch(spec_id, ROLE_REVIEWER, prompt=prompt)

    def dispatch_merger(self, spec_id, prompt=""):
        return self.dispatch(spec_id, ROLE_MERGER, prompt=prompt)

    def dequeue(self, count=1, block_ms=5000):
        """Dequeue tasks from Redis Streams."""
        if not self.redis:
            return []
        return self.redis.stream_dequeue(STREAM_QUEUE, count=count, block_ms=block_ms)

    def ack(self, message_id):
        """Acknowledge a completed task."""
        if self.redis:
            self.redis.stream_ack(STREAM_QUEUE, message_id)