"""Interface protocols for HALO-CODER loose coupling.

All domain modules depend on these abstractions, not on concrete
implementations. This enables unit testing without K3s, tmux, or a
running cluster.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainEvent:
    """A typed event with timestamp and optional payload."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = 0.0


@runtime_checkable
class EventBus(Protocol):
    """In-process publish/subscribe event bus.

    Subscribers receive typed :class:`DomainEvent` objects via bounded
    queues. Slow consumers have their oldest events dropped rather than
    blocking the publisher.
    """

    def subscribe(self) -> queue.Queue[DomainEvent]:
        """Register a new subscriber and return its event queue."""
        ...

    def unsubscribe(self, q: queue.Queue[DomainEvent]) -> None:
        """Remove a subscriber queue."""
        ...

    def publish(self, event_type: str, data: Optional[dict[str, Any]] = None) -> DomainEvent:
        """Fan an event out to every subscriber. Never raises, never blocks."""
        ...

    def subscriber_count(self) -> int:
        """Return the current number of active subscribers."""
        ...


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


@runtime_checkable
class Logger(Protocol):
    """Structured logger interface.

    Implementations must route log output to stderr (or the configured
    sink) and never use ``print()`` directly in library code.
    """

    def debug(self, msg: str, **kwargs: Any) -> None: ...
    def info(self, msg: str, **kwargs: Any) -> None: ...
    def warning(self, msg: str, **kwargs: Any) -> None: ...
    def error(self, msg: str, **kwargs: Any) -> None: ...
    def exception(self, msg: str, **kwargs: Any) -> None: ...


# ---------------------------------------------------------------------------
# Task management
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskInfo:
    """Read-only snapshot of a task's state."""

    task_id: str
    status: str
    name: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    waiting_for_input: bool = False
    parent_task_id: str = ""


@runtime_checkable
class TaskManager(Protocol):
    """Interface for spawning and monitoring agent tasks."""

    def create_task(
        self,
        name: str,
        prompt: str,
        *,
        parent_task_id: Optional[str] = None,
        assistant: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create and launch a new agent task. Returns task metadata."""
        ...

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """Retrieve task status and metadata."""
        ...

    def list_tasks(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List active and recent tasks."""
        ...

    def cancel_task(self, task_id: str) -> bool:
        """Request cancellation of a running task. Returns True if found."""
        ...


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@runtime_checkable
class MemoryStore(Protocol):
    """Interface for persistent memory CRUD and search."""

    def add(
        self,
        content: str,
        *,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Store a new memory entry. Returns the created entry."""
        ...

    def get(self, memory_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a memory entry by ID."""
        ...

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        tags: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Full-text or semantic search over stored memories."""
        ...

    def delete(self, memory_id: str) -> bool:
        """Remove a memory entry. Returns True if found."""
        ...


# ---------------------------------------------------------------------------
# Spec / TDD Pipeline
# ---------------------------------------------------------------------------


class SpecStatus(StrEnum):
    """Valid specification lifecycle status values."""

    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    RED = "red"
    GREEN = "green"
    E2E = "e2e"
    IMPLEMENTED = "implemented"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Spec:
    """A parsed specification with YAML frontmatter."""

    id: str
    title: str
    status: str = SpecStatus.DRAFT
    depends_on: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    author: str = ""
    body: str = ""
    file_path: Path = field(default_factory=Path)


@runtime_checkable
class SpecParser(Protocol):
    """Interface for parsing Markdown specs with YAML frontmatter."""

    def parse(self, content: str, *, file_path: Optional[Path] = None) -> Spec:
        """Parse a Markdown spec string into a :class:`Spec`."""
        ...

    def parse_file(self, file_path: Path) -> Spec:
        """Read and parse a spec file from disk."""
        ...


@runtime_checkable
class SpecRepository(Protocol):
    """Interface for discovering and loading specs from a Git repository."""

    def list_specs(self, *, project: str) -> list[Spec]:
        """List all specs for a project."""
        ...

    def get_spec(self, spec_id: str, *, project: str) -> Optional[Spec]:
        """Retrieve a single spec by ID."""
        ...

    def update_status(self, spec_id: str, status: str, *, project: str) -> Spec:
        """Update a spec's status and persist the change."""
        ...


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------


@runtime_checkable
class GitOps(Protocol):
    """Interface for git operations scoped to a project repository."""

    def pull(self, *, project: str) -> bool:
        """Pull latest changes. Returns True if successful."""
        ...

    def commit_and_push(
        self,
        message: str,
        *,
        project: str,
        files: Optional[list[Path]] = None,
    ) -> bool:
        """Stage, commit, and push changes. Returns True if successful."""
        ...

    def get_repo_path(self, *, project: str) -> Path:
        """Return the filesystem path to the project repository."""
        ...


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineResult:
    """Outcome of a single TDD pipeline phase."""

    phase: str
    success: bool
    task_id: str = ""
    output: str = ""
    error: str = ""


@runtime_checkable
class Supervisor(Protocol):
    """Interface for the autonomous TDD pipeline supervisor."""

    def start(self) -> None:
        """Start the supervisor background loop."""
        ...

    def stop(self) -> None:
        """Signal the supervisor to stop and wait for completion."""
        ...

    def status(self) -> dict[str, Any]:
        """Return supervisor runtime status."""
        ...

    def trigger_now(self, spec_id: str, *, project: str) -> PipelineResult:
        """Immediately trigger the pipeline for a specific spec."""
        ...


__all__ = [
    "DomainEvent",
    "EventBus",
    "Logger",
    "TaskInfo",
    "TaskManager",
    "MemoryStore",
    "SpecStatus",
    "Spec",
    "SpecParser",
    "SpecRepository",
    "GitOps",
    "PipelineResult",
    "Supervisor",
]
