#!/usr/bin/env python3
"""HALO Factory Supervisor — main event loop with inotify + HTTP API (OR-R1..OR-R8, A9).

Monitors spec directories via watchdog/inotify, reacts to status: ready transitions
within 500ms (OR-R1), dispatches agents via Redis Streams, manages DevPods via K3s API.
Runs as a host-level systemd service (A1). Includes FastAPI HTTP server at :9090 (A9).
"""

import os
import time
import threading
import logging
from pathlib import Path

from halo.common.config import HaloConfig
from halo.common.models import (
    SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_DRAFT,
    STREAM_QUEUE,
)
from halo.specs.parser import parse_specs_dir
from halo.specs.dependency_resolver import DependencyResolver
from halo.specs.state_machine import can_transition
from halo.common.logging import setup_logger


class Supervisor:
    """Main orchestrator event loop (OR-R1, OR-R2, OR-R3, OR-R8)."""

    def __init__(self, config=None, redis_client=None, k3s_client=None,
                 event_publisher=None, dispatcher=None, devpod_manager=None,
                 circuit_breaker=None, workflow=None, log=None):
        self.config = config or HaloConfig.from_env()
        self.redis = redis_client
        self.k3s = k3s_client
        self.event_publisher = event_publisher
        self.dispatcher = dispatcher
        self.devpod_manager = devpod_manager
        self.circuit_breaker = circuit_breaker
        self.workflow = workflow
        self.log = log or setup_logger("supervisor")[0]
        self._running = False
        self._paused = False
        self._watch_paths = set()
        self._last_scan = {}
        self._observer = None
        self._spec_changed = threading.Event()

    def scan_projects(self):
        """Scan all project dirs for spec files (OR-R1)."""
        specs = {}
        projects_dir = self.config.projects_dir
        if not os.path.isdir(projects_dir):
            return specs
        for project in os.listdir(projects_dir):
            specs_dir = os.path.join(projects_dir, project, "specs")
            if os.path.isdir(specs_dir):
                project_specs = parse_specs_dir(specs_dir)
                for spec_id, spec in project_specs.items():
                    spec._project = project
                    specs[spec_id] = spec
        return specs

    def detect_ready_specs(self, specs):
        """Find specs with status: ready that are unblocked and ready to dispatch."""
        resolver = DependencyResolver(specs)
        runnable = resolver.get_runnable_specs()
        ready_specs = []
        for spec_id in runnable:
            spec = specs[spec_id]
            if spec.status == SPEC_STATUS_READY:
                if resolver.can_start(spec_id):
                    ready_specs.append(spec_id)
        return ready_specs

    def handle_spec_change(self, spec_id, spec):
        """Handle a spec status change — dispatch work if ready (WF-SPEC-3..4)."""
        if spec.status == SPEC_STATUS_READY:
            if self.workflow:
                self.workflow.start_spec(spec_id, spec)
                self.log.info(f"Dispatched spec {spec_id}", extra={"component": "supervisor", "spec_id": spec_id})

    def on_spec_changed(self, file_path):
        """Called by inotify watcher when a spec file changes (OR-R1 <500ms)."""
        self._spec_changed.set()
        self.log.info(f"Spec file changed: {file_path}", extra={"component": "supervisor"})

    def _setup_inotify(self):
        """Set up watchdog filesystem watchers for all project spec dirs."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class SpecHandler(FileSystemEventHandler):
                def __init__(self, supervisor):
                    self.supervisor = supervisor
                def on_modified(self, event):
                    if not event.is_directory and event.src_path.endswith(".md"):
                        self.supervisor.on_spec_changed(event.src_path)
                def on_created(self, event):
                    if not event.is_directory and event.src_path.endswith(".md"):
                        self.supervisor.on_spec_changed(event.src_path)

            self._observer = Observer()
            handler = SpecHandler(self)
            projects_dir = self.config.projects_dir
            if os.path.isdir(projects_dir):
                for project in os.listdir(projects_dir):
                    specs_dir = os.path.join(projects_dir, project, "specs")
                    if os.path.isdir(specs_dir):
                        self._watch_paths.add(specs_dir)
                        self._observer.schedule(handler, specs_dir, recursive=False)
            self._observer.start()
            self.log.info(f"Inotify watching {len(self._watch_paths)} spec dirs", extra={"component": "supervisor"})
        except ImportError:
            self.log.warning("watchdog not installed, falling back to polling", extra={"component": "supervisor"})
            self._observer = None

    def run(self, poll_interval=1.0, with_api=True):
        """Main supervisor event loop (OR-NF1: ≤1s p99).

        If with_api=True, starts the HTTP API server (:9090) in a background thread
        and uses inotify for spec file watching. Falls back to polling if watchdog
        is not available.
        """
        self._running = True
        self.log.info("Supervisor started", extra={"component": "supervisor"})

        if with_api:
            self._start_api_server()

        self._setup_inotify()

        while self._running:
            if self._paused:
                time.sleep(poll_interval)
                continue
            try:
                if self._spec_changed.is_set() or self._observer is None:
                    self._spec_changed.clear()
                    specs = self.scan_projects()
                    ready = self.detect_ready_specs(specs)
                    for spec_id in ready:
                        self.handle_spec_change(spec_id, specs[spec_id])
                    if self.redis and not self._last_scan:
                        self.recover_in_progress(specs)
                    self._last_scan = {sid: s.status for sid, s in specs.items()}
            except Exception as e:
                self.log.error(f"Supervisor loop error: {e}", extra={"component": "supervisor"})
            if self._observer is not None:
                self._spec_changed.wait(timeout=poll_interval)
            else:
                time.sleep(poll_interval)

        if self._observer:
            self._observer.stop()
            self._observer.join()

    def _start_api_server(self):
        """Start the Supervisor HTTP API in a background thread (A9)."""
        from halo.factory.supervisor_api import app as api_app
        import uvicorn

        api_app.state.supervisor = self

        config = uvicorn.Config(
            api_app,
            host="0.0.0.0",
            port=int(os.environ.get("HALO_SUPERVISOR_PORT", "9090")),
            log_level="warning",
        )
        server = uvicorn.Server(config)

        def run_server():
            server.run()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        self.log.info(f"Supervisor API on :{os.environ.get('HALO_SUPERVISOR_PORT', '9090')}", extra={"component": "supervisor"})

    def recover_in_progress(self, specs):
        """Recover in_progress specs on startup (OR-R8)."""
        from halo.factory.recovery import Recovery
        recovery = Recovery(self.k3s, self.event_publisher, self.log)
        for spec_id, spec in specs.items():
            if spec.status == SPEC_STATUS_IN_PROGRESS:
                recovery.check_and_resume(spec_id, spec)

    def pause(self):
        """Pause the supervisor event loop (maintenance mode)."""
        self._paused = True
        self.log.info("Supervisor paused (maintenance mode)", extra={"component": "supervisor"})

    def resume(self):
        """Resume the supervisor event loop."""
        self._paused = False
        self.log.info("Supervisor resumed", extra={"component": "supervisor"})

    def stop(self):
        """Stop the supervisor event loop."""
        self._running = False
        self._spec_changed.set()
        self.log.info("Supervisor stopping", extra={"component": "supervisor"})


if __name__ == "__main__":
    supervisor = Supervisor()
    supervisor.run()