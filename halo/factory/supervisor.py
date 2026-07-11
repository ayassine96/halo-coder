#!/usr/bin/env python3
"""HALO Factory Supervisor — main event loop (OR-R1..OR-R8).

Monitors spec directories via inotify/watchdog, reacts to status: ready transitions
within 500ms, dispatches agents via Redis Streams, manages DevPods via K3s API.
Runs as a host-level systemd service (A1).
"""

import os
import time
import json
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

    def run(self, poll_interval=1.0):
        """Main supervisor event loop (OR-NF1: ≤1s p99)."""
        self._running = True
        self.log.info("Supervisor started", extra={"component": "supervisor"})
        while self._running:
            if self._paused:
                time.sleep(poll_interval)
                continue
            try:
                specs = self.scan_projects()
                ready = self.detect_ready_specs(specs)
                for spec_id in ready:
                    self.handle_spec_change(spec_id, specs[spec_id])
                if self.redis and not self._last_scan:
                    self.recover_in_progress(specs)
                self._last_scan = {sid: s.status for sid, s in specs.items()}
            except Exception as e:
                self.log.error(f"Supervisor loop error: {e}", extra={"component": "supervisor"})
            time.sleep(poll_interval)

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
        self.log.info("Supervisor stopping", extra={"component": "supervisor"})


if __name__ == "__main__":
    supervisor = Supervisor()
    supervisor.run()