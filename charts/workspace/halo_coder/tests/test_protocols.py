"""Tests for the halo_coder.protocols module."""

from __future__ import annotations

import queue
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

from halo_coder.protocols import (
    DomainEvent,
    EventBus,
    GitOps,
    Logger,
    MemoryStore,
    PipelineResult,
    Spec,
    SpecParser,
    SpecRepository,
    SpecStatus,
    Supervisor,
    TaskInfo,
    TaskManager,
)


class FakeEventBus:
    def subscribe(self) -> "queue.Queue[DomainEvent]":
        return queue.Queue()

    def unsubscribe(self, q: "queue.Queue[DomainEvent]") -> None:
        pass

    def publish(
        self, event_type: str, data: dict[str, Any] | None = None
    ) -> DomainEvent:
        return DomainEvent(type=event_type)

    def subscriber_count(self) -> int:
        return 0


class FakeLogger:
    def debug(self, msg: str, **kwargs: Any) -> None: pass
    def info(self, msg: str, **kwargs: Any) -> None: pass
    def warning(self, msg: str, **kwargs: Any) -> None: pass
    def error(self, msg: str, **kwargs: Any) -> None: pass
    def exception(self, msg: str, **kwargs: Any) -> None: pass


class TestRuntimeCheckable(unittest.TestCase):
    def test_eventbus_protocol_detects_conformance(self) -> None:
        self.assertIsInstance(FakeEventBus(), EventBus)

    def test_eventbus_protocol_rejects_nonconforming(self) -> None:
        class NotBus:
            pass
        self.assertNotIsInstance(NotBus(), EventBus)

    def test_logger_protocol_detects_conformance(self) -> None:
        self.assertIsInstance(FakeLogger(), Logger)

    def test_logger_protocol_rejects_nonconforming(self) -> None:
        class NotLogger:
            pass
        self.assertNotIsInstance(NotLogger(), Logger)


class TestDomainEvent(unittest.TestCase):
    def test_defaults(self) -> None:
        e = DomainEvent(type="test")
        self.assertEqual(e.type, "test")
        self.assertEqual(e.data, {})
        self.assertEqual(e.ts, 0.0)

    def test_with_data_and_ts(self) -> None:
        e = DomainEvent(type="x", data={"k": "v"}, ts=123.456)
        self.assertEqual(e.data["k"], "v")
        self.assertEqual(e.ts, 123.456)

    def test_is_frozen(self) -> None:
        e = DomainEvent(type="x")
        with self.assertRaises(FrozenInstanceError):
            e.type = "y"  # type: ignore[misc]


class TestTaskInfo(unittest.TestCase):
    def test_defaults(self) -> None:
        t = TaskInfo(task_id="t1", status="running")
        self.assertEqual(t.task_id, "t1")
        self.assertEqual(t.status, "running")
        self.assertEqual(t.name, "")
        self.assertEqual(t.parent_task_id, "")

    def test_is_frozen(self) -> None:
        t = TaskInfo(task_id="t1", status="running")
        with self.assertRaises(FrozenInstanceError):
            t.status = "done"  # type: ignore[misc]


class TestSpec(unittest.TestCase):
    def test_defaults(self) -> None:
        s = Spec(id="s1", title="Test Spec")
        self.assertEqual(s.id, "s1")
        self.assertEqual(s.title, "Test Spec")
        self.assertEqual(s.status, SpecStatus.DRAFT)
        self.assertEqual(s.depends_on, [])
        self.assertEqual(s.blocks, [])
        self.assertEqual(s.tags, [])

    def test_custom_status(self) -> None:
        s = Spec(id="s2", title="Ready Spec", status=SpecStatus.READY)
        self.assertEqual(s.status, "ready")

    def test_is_frozen(self) -> None:
        s = Spec(id="s1", title="T")
        with self.assertRaises(FrozenInstanceError):
            s.status = "ready"  # type: ignore[misc]


class TestPipelineResult(unittest.TestCase):
    def test_defaults(self) -> None:
        pr = PipelineResult(phase="red", success=True)
        self.assertEqual(pr.phase, "red")
        self.assertTrue(pr.success)
        self.assertEqual(pr.task_id, "")
        self.assertEqual(pr.output, "")

    def test_is_frozen(self) -> None:
        pr = PipelineResult(phase="green", success=True)
        with self.assertRaises(FrozenInstanceError):
            pr.success = False  # type: ignore[misc]


class TestSpecStatus(unittest.TestCase):
    def test_all_statuses_defined(self) -> None:
        expected = {
            "draft", "ready", "in_progress", "red", "green",
            "e2e", "implemented", "failed", "blocked",
        }
        actual = {m.value for m in SpecStatus.__members__.values()}
        self.assertEqual(actual, expected)

    def test_members_are_str_enum(self) -> None:
        self.assertIsInstance(SpecStatus.DRAFT, str)
        self.assertIsInstance(SpecStatus.READY, str)
        self.assertEqual(SpecStatus.DRAFT, "draft")
        self.assertEqual(SpecStatus.IMPLEMENTED, "implemented")


class TestSpecParserProtocol(unittest.TestCase):
    def test_mock_parser(self) -> None:
        class Parser:
            def parse(self, content: str, *, file_path: Path | None = None) -> Spec:
                return Spec(id="x", title="y")
            def parse_file(self, file_path: Path) -> Spec:
                return Spec(id="x", title="y")

        self.assertIsInstance(Parser(), SpecParser)


class TestSpecRepositoryProtocol(unittest.TestCase):
    def test_mock_repo(self) -> None:
        class Repo:
            def list_specs(self, *, project: str) -> list[Spec]:
                return []
            def get_spec(self, spec_id: str, *, project: str) -> Spec | None:
                return None
            def update_status(self, spec_id: str, status: str, *, project: str) -> Spec:
                return Spec(id=spec_id, title="x", status=status)

        self.assertIsInstance(Repo(), SpecRepository)


class TestGitOpsProtocol(unittest.TestCase):
    def test_mock_git(self) -> None:
        class Git:
            def pull(self, *, project: str) -> bool:
                return True
            def commit_and_push(self, message: str, *, project: str, files: list[Path] | None = None) -> bool:
                return True
            def get_repo_path(self, *, project: str) -> Path:
                return Path("/repos/p")

        self.assertIsInstance(Git(), GitOps)


class TestSupervisorProtocol(unittest.TestCase):
    def test_mock_supervisor(self) -> None:
        class Sup:
            def start(self) -> None: pass
            def stop(self) -> None: pass
            def status(self) -> dict[str, Any]:
                return {}
            def trigger_now(self, spec_id: str, *, project: str) -> PipelineResult:
                return PipelineResult(phase="done", success=True)

        self.assertIsInstance(Sup(), Supervisor)


class TestTaskManagerProtocol(unittest.TestCase):
    def test_mock_task_manager(self) -> None:
        class TM:
            def create_task(self, name: str, prompt: str, *, parent_task_id: str | None = None, assistant: str | None = None) -> dict[str, Any]:
                return {}
            def get_task(self, task_id: str) -> dict[str, Any] | None:
                return None
            def list_tasks(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
                return []
            def cancel_task(self, task_id: str) -> bool:
                return True

        self.assertIsInstance(TM(), TaskManager)


class TestMemoryStoreProtocol(unittest.TestCase):
    def test_mock_memory_store(self) -> None:
        class MS:
            def add(self, content: str, *, tags: list[str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
                return {}
            def get(self, memory_id: str) -> dict[str, Any] | None:
                return None
            def search(self, query: str, *, limit: int = 10, tags: list[str] | None = None) -> list[dict[str, Any]]:
                return []
            def delete(self, memory_id: str) -> bool:
                return True

        self.assertIsInstance(MS(), MemoryStore)
