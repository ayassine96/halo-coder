#!/usr/bin/env python3
"""Shared Pydantic models for HALO Factory services."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


SPEC_STATUS_DRAFT = "draft"
SPEC_STATUS_READY = "ready"
SPEC_STATUS_IN_PROGRESS = "in_progress"
SPEC_STATUS_IMPLEMENTED = "implemented"
SPEC_STATUS_MERGED = "merged"
SPEC_STATUS_FAILED_RED = "failed_red"
SPEC_STATUS_FAILED_GREEN = "failed_green"
SPEC_STATUS_FAILED_E2E = "failed_e2e"

ALL_STATUSES = [
    SPEC_STATUS_DRAFT,
    SPEC_STATUS_READY,
    SPEC_STATUS_IN_PROGRESS,
    SPEC_STATUS_IMPLEMENTED,
    SPEC_STATUS_MERGED,
    SPEC_STATUS_FAILED_RED,
    SPEC_STATUS_FAILED_GREEN,
    SPEC_STATUS_FAILED_E2E,
]


@dataclass
class Spec:
    """A parsed spec file."""
    id: str
    title: str
    status: str
    depends_on: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    author: str = "halo-agent"
    created_at: str = ""
    body: str = ""
    file_path: str = ""

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "depends_on": self.depends_on,
            "blocks": self.blocks,
            "tags": self.tags,
            "author": self.author,
            "created_at": self.created_at,
            "body": self.body,
            "file_path": self.file_path,
        }


@dataclass
class TdadRequest:
    repo: str
    changed_files: list
    spec_id: str = ""


@dataclass
class TdadResponse:
    affected_tests: list = field(default_factory=list)
    confidence: float = 0.0
    uncovered_paths: list = field(default_factory=list)


@dataclass
class ModelProfile:
    name: str
    model_path: str
    quantization: str = "Q4_K_M"
    max_num_seqs: int = 1
    gpu_memory_utilization: float = 0.9


@dataclass
class AgentTask:
    spec_id: str
    role: str
    model_profile: str
    prompt: str = ""
    tools: list = field(default_factory=list)
    branch: str = ""

    def stream_key(self):
        return f"halo:factory:queue:{self.spec_id}"


@dataclass
class EventMessage:
    channel: str
    event_type: str
    spec_id: str = ""
    data: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


CHANNEL_LOGS = "halo:factory:logs"
CHANNEL_APPROVALS = "halo:factory:approvals"
CHANNEL_ALERTS = "halo:factory:alerts"
CHANNEL_METRICS = "halo:factory:metrics"
STREAM_QUEUE = "halo:factory:queue"