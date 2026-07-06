"""Configuration subsystem.

Parses environment variables and YAML values into a frozen, validated
AppConfig dataclass. All configuration is injected — no global mutable state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class AuthMode(str, Enum):
    """Authentication mode for the workspace."""

    BASIC = "basic"
    OAUTH2 = "oauth2"
    NONE = "none"


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""

    NONE = "none"
    VOYAGE = "voyage"
    OPENAI = "openai"


@dataclass(frozen=True)
class AlertThreshold:
    """Threshold pair for a single metric dimension."""

    warning: float
    critical: float


@dataclass(frozen=True)
class AlertThresholds:
    """Alert thresholds for system metrics."""

    cpu: AlertThreshold = field(default_factory=lambda: AlertThreshold(warning=70.0, critical=90.0))
    memory: AlertThreshold = field(default_factory=lambda: AlertThreshold(warning=80.0, critical=95.0))
    disk: AlertThreshold = field(default_factory=lambda: AlertThreshold(warning=80.0, critical=90.0))


@dataclass(frozen=True)
class MemoryConfig:
    """Configuration for the persistent memory subsystem."""

    db_path: Path = Path("/home/dev/.claude-memory/memory.db")
    embeddings_provider: EmbeddingProvider = EmbeddingProvider.NONE
    inject_enabled: bool = True
    consolidation_enabled: bool = False
    embed_interval_seconds: int = 30
    gc_days: float = 0.0
    gc_interval_hours: float = 12.0
    preinject_enabled: bool = True


@dataclass(frozen=True)
class SupervisorConfig:
    """Configuration for the autonomous spec supervisor."""

    poll_interval_seconds: int = 10
    max_concurrent_tasks: int = 12
    tasks_dir: Path = Path("/home/dev/.claude-tasks")
    projects_dir: Path = Path("/var/halo/projects")


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration.

    All values are derived from environment variables with validated defaults.
    Instances should be created via :func:`load_config` rather than directly.
    """

    readonly_mode: bool = False
    auth_mode: AuthMode = AuthMode.BASIC
    demo_show_all: bool = False
    trusted_proxy: bool = True
    max_request_body_bytes: int = 1_048_576
    stream_max_seconds: int = 1_800
    allow_internal_hooks: bool = False
    controller_self_serve_url: str = ""
    controller_self_serve_token: str = ""
    idle_waiting_seconds: float = 90.0
    alert_thresholds: AlertThresholds = field(default_factory=AlertThresholds)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    supervisor: SupervisorConfig = field(default_factory=SupervisorConfig)
    dashboard_dist_dir: Path = Path("/opt/dashboard-dist")
    workspace_user: str = ""


def load_config(
    *,
    env: Optional[dict[str, str]] = None,
    overrides: Optional[dict[str, object]] = None,
) -> AppConfig:
    """Load and validate application configuration from the environment.

    Args:
        env: Optional environment dict (defaults to ``os.environ``).
        overrides: Optional key-value overrides for testing.

    Returns:
        A frozen :class:`AppConfig` instance.

    Raises:
        ValueError: If safety invariants are violated (e.g. auth=none
                    without readonly mode).
    """
    import os as _os

    environ = env if env is not None else _os.environ

    def _bool(key: str, default: str) -> bool:
        return environ.get(key, default).lower() == "true"

    def _int(key: str, default: str) -> int:
        return int(environ.get(key, default))

    def _float(key: str, default: str) -> float:
        raw = environ.get(key, default)
        try:
            return float(raw)
        except ValueError:
            import sys
            print(
                f"[halo_coder.config] WARNING: {key}={raw!r} is not a valid "
                f"float, falling back to default {default!r}",
                file=sys.stderr,
            )
            return float(default)

    config = AppConfig(
        readonly_mode=_bool("READONLY_MODE", "false"),
        auth_mode=AuthMode(environ.get("AUTH_MODE", "basic").lower()),
        demo_show_all=_bool("DEMO_SHOW_ALL", "false"),
        trusted_proxy=_bool("TRUSTED_PROXY", "true"),
        max_request_body_bytes=_int("MAX_REQUEST_BODY_BYTES", "1048576"),
        stream_max_seconds=_int("STREAM_MAX_SECONDS", "1800"),
        allow_internal_hooks=_bool("ALLOW_INTERNAL_HOOKS", "false"),
        controller_self_serve_url=environ.get("CONTROLLER_SELF_SERVE_URL", "").strip().rstrip("/"),
        controller_self_serve_token=environ.get("CONTROLLER_SELF_SERVE_TOKEN", "").strip(),
        idle_waiting_seconds=_float("KC_IDLE_WAITING_SECONDS", "90"),
        alert_thresholds=AlertThresholds(
            cpu=AlertThreshold(
                warning=_float("KC_ALERT_CPU_WARNING", "70"),
                critical=_float("KC_ALERT_CPU_CRITICAL", "90"),
            ),
            memory=AlertThreshold(
                warning=_float("KC_ALERT_MEMORY_WARNING", "80"),
                critical=_float("KC_ALERT_MEMORY_CRITICAL", "95"),
            ),
            disk=AlertThreshold(
                warning=_float("KC_ALERT_DISK_WARNING", "80"),
                critical=_float("KC_ALERT_DISK_CRITICAL", "90"),
            ),
        ),
        memory=MemoryConfig(
            db_path=Path(environ.get("KC_MEMORY_DB_PATH", "/home/dev/.claude-memory/memory.db")),
            embeddings_provider=EmbeddingProvider(
                environ.get("KC_MEMORY_EMBEDDINGS_PROVIDER", "none").lower()
            ),
            inject_enabled=_bool("KC_MEMORY_INJECT_ENABLED", "true"),
            consolidation_enabled=_bool("KC_MEMORY_CONSOLIDATION_ENABLED", "false"),
            embed_interval_seconds=_int("KC_EMBED_INTERVAL", "30"),
            gc_days=_float("KC_MEMORY_GC_DAYS", "0"),
            gc_interval_hours=_float("KC_MEMORY_GC_INTERVAL_H", "12"),
            preinject_enabled=_bool("KC_MEMORY_PREINJECT", "true"),
        ),
        supervisor=SupervisorConfig(
            poll_interval_seconds=_int("KC_SUPERVISOR_POLL_INTERVAL", "10"),
            max_concurrent_tasks=_int("KC_MAX_TASKS", "12"),
            tasks_dir=Path(environ.get("KC_TASKS_DIR", "/home/dev/.claude-tasks")),
            projects_dir=Path(environ.get("KC_PROJECTS_DIR", "/var/halo/projects")),
        ),
        dashboard_dist_dir=Path(environ.get("DASHBOARD_DIST_DIR", "/opt/dashboard-dist")),
        workspace_user=environ.get("WORKSPACE_USER", "").strip(),
    )

    if overrides:
        config = _apply_overrides(config, overrides)

    _check_safety_invariants(config)
    return config


def _apply_overrides(config: AppConfig, overrides: dict[str, object]) -> AppConfig:
    """Apply a dict of overrides to an AppConfig, returning a new instance.

    Supports shallow overrides of top-level fields only. Nested dataclass
    fields (``memory``, ``supervisor``, ``alert_thresholds``) must be
    replaced wholesale rather than merged recursively.
    """
    kwargs: dict[str, object] = {}
    for f in AppConfig.__dataclass_fields__.values():
        if f.name in overrides:
            kwargs[f.name] = overrides[f.name]
        else:
            kwargs[f.name] = getattr(config, f.name)
    return AppConfig(**kwargs)


def _check_safety_invariants(config: AppConfig) -> None:
    """Validate configuration safety invariants.

    Raises:
        ValueError: If the configuration is unsafe.
    """
    if config.auth_mode == AuthMode.NONE and not config.readonly_mode:
        raise ValueError(
            "AUTH_MODE=none requires READONLY_MODE=true. "
            "Refusing an unauthenticated, writable workspace."
        )
    if config.max_request_body_bytes < 1:
        raise ValueError(
            f"MAX_REQUEST_BODY_BYTES must be positive, got {config.max_request_body_bytes}"
        )
    if config.idle_waiting_seconds <= 0:
        raise ValueError(
            f"KC_IDLE_WAITING_SECONDS must be positive, got {config.idle_waiting_seconds}"
        )


__all__ = [
    "AppConfig",
    "AuthMode",
    "EmbeddingProvider",
    "AlertThreshold",
    "AlertThresholds",
    "MemoryConfig",
    "SupervisorConfig",
    "load_config",
]
