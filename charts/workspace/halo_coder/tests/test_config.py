"""Tests for the halo_coder.config module."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from halo_coder.config import (
    AppConfig,
    AuthMode,
    EmbeddingProvider,
    AlertThreshold,
    AlertThresholds,
    MemoryConfig,
    SupervisorConfig,
    load_config,
)


class TestAuthMode(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(AuthMode.BASIC, "basic")
        self.assertEqual(AuthMode.OAUTH2, "oauth2")
        self.assertEqual(AuthMode.NONE, "none")

    def test_from_string(self) -> None:
        self.assertEqual(AuthMode("basic"), AuthMode.BASIC)
        self.assertEqual(AuthMode("oauth2"), AuthMode.OAUTH2)
        self.assertEqual(AuthMode("none"), AuthMode.NONE)

    def test_invalid_value_raises(self) -> None:
        with self.assertRaises(ValueError):
            AuthMode("invalid")


class TestEmbeddingProvider(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(EmbeddingProvider.NONE, "none")
        self.assertEqual(EmbeddingProvider.VOYAGE, "voyage")
        self.assertEqual(EmbeddingProvider.OPENAI, "openai")

    def test_from_string(self) -> None:
        self.assertEqual(EmbeddingProvider("none"), EmbeddingProvider.NONE)
        self.assertEqual(EmbeddingProvider("voyage"), EmbeddingProvider.VOYAGE)
        self.assertEqual(EmbeddingProvider("openai"), EmbeddingProvider.OPENAI)

    def test_invalid_value_raises(self) -> None:
        with self.assertRaises(ValueError):
            EmbeddingProvider("invalid")


class TestAlertThreshold(unittest.TestCase):
    def test_defaults(self) -> None:
        t = AlertThreshold(warning=70.0, critical=90.0)
        self.assertEqual(t.warning, 70.0)
        self.assertEqual(t.critical, 90.0)

    def test_immutable(self) -> None:
        t = AlertThreshold(warning=50.0, critical=80.0)
        with self.assertRaises(FrozenInstanceError):
            t.warning = 99.0  # type: ignore[misc]


class TestAlertThresholds(unittest.TestCase):
    def test_defaults(self) -> None:
        thresholds = AlertThresholds()
        self.assertEqual(thresholds.cpu.warning, 70.0)
        self.assertEqual(thresholds.cpu.critical, 90.0)
        self.assertEqual(thresholds.memory.warning, 80.0)
        self.assertEqual(thresholds.memory.critical, 95.0)
        self.assertEqual(thresholds.disk.warning, 80.0)
        self.assertEqual(thresholds.disk.critical, 90.0)


class TestMemoryConfig(unittest.TestCase):
    def test_defaults(self) -> None:
        cfg = MemoryConfig()
        self.assertEqual(str(cfg.db_path), "/home/dev/.claude-memory/memory.db")
        self.assertEqual(cfg.embeddings_provider, EmbeddingProvider.NONE)
        self.assertTrue(cfg.inject_enabled)
        self.assertFalse(cfg.consolidation_enabled)


class TestSupervisorConfig(unittest.TestCase):
    def test_defaults(self) -> None:
        cfg = SupervisorConfig()
        self.assertEqual(cfg.poll_interval_seconds, 10)
        self.assertEqual(cfg.max_concurrent_tasks, 12)
        self.assertEqual(str(cfg.tasks_dir), "/home/dev/.claude-tasks")
        self.assertEqual(str(cfg.projects_dir), "/var/halo/projects")


class TestAppConfigDefaults(unittest.TestCase):
    def test_frozen_dataclass(self) -> None:
        cfg = AppConfig()
        self.assertFalse(cfg.readonly_mode)
        self.assertEqual(cfg.auth_mode, AuthMode.BASIC)
        self.assertEqual(cfg.max_request_body_bytes, 1_048_576)
        self.assertEqual(cfg.stream_max_seconds, 1_800)

    def test_immutable(self) -> None:
        cfg = AppConfig()
        with self.assertRaises(FrozenInstanceError):
            cfg.readonly_mode = True  # type: ignore[misc]


class TestLoadConfig(unittest.TestCase):
    def test_defaults_from_empty_env(self) -> None:
        cfg = load_config(env={})
        self.assertIsInstance(cfg, AppConfig)
        self.assertFalse(cfg.readonly_mode)
        self.assertEqual(cfg.auth_mode, AuthMode.BASIC)

    def test_readonly_mode_enabled(self) -> None:
        cfg = load_config(env={"READONLY_MODE": "true"})
        self.assertTrue(cfg.readonly_mode)

    def test_readonly_mode_disabled(self) -> None:
        cfg = load_config(env={"READONLY_MODE": "false"})
        self.assertFalse(cfg.readonly_mode)

    def test_auth_mode_basic(self) -> None:
        cfg = load_config(env={"AUTH_MODE": "basic"})
        self.assertEqual(cfg.auth_mode, AuthMode.BASIC)

    def test_auth_mode_oauth2(self) -> None:
        cfg = load_config(env={"AUTH_MODE": "oauth2"})
        self.assertEqual(cfg.auth_mode, AuthMode.OAUTH2)

    def test_auth_mode_none_with_readonly(self) -> None:
        cfg = load_config(env={"AUTH_MODE": "none", "READONLY_MODE": "true"})
        self.assertEqual(cfg.auth_mode, AuthMode.NONE)
        self.assertTrue(cfg.readonly_mode)

    def test_auth_mode_none_without_readonly_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            load_config(env={"AUTH_MODE": "none", "READONLY_MODE": "false"})
        self.assertIn("AUTH_MODE=none", str(ctx.exception))

    def test_auth_mode_case_insensitive(self) -> None:
        cfg = load_config(env={"AUTH_MODE": "NONE", "READONLY_MODE": "true"})
        self.assertEqual(cfg.auth_mode, AuthMode.NONE)

    def test_demo_show_all(self) -> None:
        cfg = load_config(env={"DEMO_SHOW_ALL": "true"})
        self.assertTrue(cfg.demo_show_all)

    def test_demo_show_all_default_false(self) -> None:
        cfg = load_config(env={})
        self.assertFalse(cfg.demo_show_all)

    def test_trusted_proxy(self) -> None:
        cfg = load_config(env={"TRUSTED_PROXY": "false"})
        self.assertFalse(cfg.trusted_proxy)

    def test_max_request_body_bytes(self) -> None:
        cfg = load_config(env={"MAX_REQUEST_BODY_BYTES": "2048"})
        self.assertEqual(cfg.max_request_body_bytes, 2048)

    def test_max_request_body_bytes_default(self) -> None:
        cfg = load_config(env={})
        self.assertEqual(cfg.max_request_body_bytes, 1_048_576)

    def test_stream_max_seconds(self) -> None:
        cfg = load_config(env={"STREAM_MAX_SECONDS": "3600"})
        self.assertEqual(cfg.stream_max_seconds, 3600)

    def test_allow_internal_hooks(self) -> None:
        cfg = load_config(env={"ALLOW_INTERNAL_HOOKS": "true"})
        self.assertTrue(cfg.allow_internal_hooks)

    def test_controller_url(self) -> None:
        cfg = load_config(env={"CONTROLLER_SELF_SERVE_URL": "http://example.com/api/"})
        self.assertEqual(cfg.controller_self_serve_url, "http://example.com/api")

    def test_controller_url_trailing_slash_stripped(self) -> None:
        cfg = load_config(env={"CONTROLLER_SELF_SERVE_URL": "http://example.com/api/"})
        self.assertEqual(cfg.controller_self_serve_url, "http://example.com/api")

    def test_idle_waiting_seconds(self) -> None:
        cfg = load_config(env={"KC_IDLE_WAITING_SECONDS": "120"})
        self.assertEqual(cfg.idle_waiting_seconds, 120.0)

    def test_idle_waiting_seconds_invalid_falls_back(self) -> None:
        cfg = load_config(env={"KC_IDLE_WAITING_SECONDS": "not-a-number"})
        self.assertEqual(cfg.idle_waiting_seconds, 90.0)

    def test_alert_thresholds_env(self) -> None:
        cfg = load_config(
            env={
                "KC_ALERT_CPU_WARNING": "75",
                "KC_ALERT_CPU_CRITICAL": "92",
                "KC_ALERT_MEMORY_WARNING": "85",
                "KC_ALERT_MEMORY_CRITICAL": "98",
                "KC_ALERT_DISK_WARNING": "82",
                "KC_ALERT_DISK_CRITICAL": "95",
            }
        )
        self.assertEqual(cfg.alert_thresholds.cpu.warning, 75.0)
        self.assertEqual(cfg.alert_thresholds.cpu.critical, 92.0)
        self.assertEqual(cfg.alert_thresholds.memory.warning, 85.0)
        self.assertEqual(cfg.alert_thresholds.memory.critical, 98.0)

    def test_memory_config_env(self) -> None:
        cfg = load_config(
            env={
                "KC_MEMORY_DB_PATH": "/tmp/memory.db",
                "KC_MEMORY_EMBEDDINGS_PROVIDER": "voyage",
                "KC_MEMORY_INJECT_ENABLED": "false",
                "KC_MEMORY_CONSOLIDATION_ENABLED": "true",
            }
        )
        self.assertEqual(str(cfg.memory.db_path), "/tmp/memory.db")
        self.assertEqual(cfg.memory.embeddings_provider, EmbeddingProvider.VOYAGE)
        self.assertFalse(cfg.memory.inject_enabled)
        self.assertTrue(cfg.memory.consolidation_enabled)

    def test_supervisor_config_env(self) -> None:
        cfg = load_config(
            env={
                "KC_SUPERVISOR_POLL_INTERVAL": "30",
                "KC_MAX_TASKS": "8",
                "KC_TASKS_DIR": "/tmp/tasks",
                "KC_PROJECTS_DIR": "/tmp/projects",
            }
        )
        self.assertEqual(cfg.supervisor.poll_interval_seconds, 30)
        self.assertEqual(cfg.supervisor.max_concurrent_tasks, 8)
        self.assertEqual(str(cfg.supervisor.tasks_dir), "/tmp/tasks")
        self.assertEqual(str(cfg.supervisor.projects_dir), "/tmp/projects")

    def test_workspace_user(self) -> None:
        cfg = load_config(env={"WORKSPACE_USER": "testuser"})
        self.assertEqual(cfg.workspace_user, "testuser")

    def test_overrides(self) -> None:
        cfg = load_config(env={}, overrides={"readonly_mode": True, "workspace_user": "override"})
        self.assertTrue(cfg.readonly_mode)
        self.assertEqual(cfg.workspace_user, "override")

    def test_max_request_body_bytes_negative_raises(self) -> None:
        with self.assertRaises(ValueError):
            load_config(env={"MAX_REQUEST_BODY_BYTES": "-1"})

    def test_idle_waiting_seconds_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            load_config(env={"KC_IDLE_WAITING_SECONDS": "0"})


class TestLoadConfigRealEnv(unittest.TestCase):
    """Sanity checks against the real process environment."""

    def test_loads_without_crashing(self) -> None:
        cfg = load_config()
        self.assertIsInstance(cfg, AppConfig)
        self.assertIsInstance(cfg.auth_mode, AuthMode)

    def test_loads_in_this_test_environment(self) -> None:
        cfg = load_config()
        self.assertIsNotNone(cfg.max_request_body_bytes)
        self.assertIsNotNone(cfg.stream_max_seconds)
