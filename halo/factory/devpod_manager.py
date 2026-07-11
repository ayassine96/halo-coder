#!/usr/bin/env python3
"""DevPod manager — K3s lifecycle for agent DevPods (OR-R7, DP-R9).

Scale up when work is available, destroy idle pods after 30 min.
Agent DevPods are ephemeral; destroyed after task completion + 5-min grace.
"""

import time
from datetime import datetime, timezone


IDLE_THRESHOLD_SECONDS = 30 * 60  # 30 minutes (OR-R7)
GRACE_PERIOD_SECONDS = 5 * 60     # 5 minutes after task completion (DP-R9)


class DevPodManager:
    """Manage DevPod scaling and lifecycle via K3s API."""

    def __init__(self, k3s_client=None, max_devpods=2, log=None):
        self.k3s = k3s_client
        self.max_devpods = max_devpods
        self.log = log
        self._active_devpods = {}  # spec_id → {name, started_at, last_active}
        self._idle_timers = {}

    def scale_up(self, spec_id, template="python-default"):
        """Scale up a DevPod for a spec (OR-R7)."""
        if len(self._active_devpods) >= self.max_devpods:
            return None, "Max DevPods reached"
        name = f"halo-devpod-{spec_id.lower()}"
        if self.k3s:
            self.k3s.scale_deployment(name, 1)
        self._active_devpods[spec_id] = {
            "name": name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_active": time.time(),
            "status": "running",
        }
        return name, None

    def scale_down(self, spec_id):
        """Scale down a DevPod (OR-R7)."""
        if spec_id not in self._active_devpods:
            return False
        info = self._active_devpods[spec_id]
        name = info["name"]
        if self.k3s:
            self.k3s.scale_deployment(name, 0)
        info["status"] = "stopping"
        info["stopped_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def destroy(self, spec_id):
        """Destroy a DevPod (DP-R9)."""
        info = self._active_devpods.pop(spec_id, None)
        if not info:
            return False
        name = info["name"]
        if self.k3s:
            self.k3s.delete_pod(name)
        return True

    def touch(self, spec_id):
        """Update last_active timestamp for a DevPod."""
        if spec_id in self._active_devpods:
            self._active_devpods[spec_id]["last_active"] = time.time()

    def cleanup_idle(self):
        """Destroy DevPods idle for > 30 min (OR-R7)."""
        now = time.time()
        to_destroy = []
        for spec_id, info in list(self._active_devpods.items()):
            idle_time = now - info.get("last_active", now)
            if idle_time > IDLE_THRESHOLD_SECONDS:
                to_destroy.append(spec_id)
        for spec_id in to_destroy:
            self.destroy(spec_id)
        return to_destroy

    def get_status(self, spec_id=None):
        """Return DevPod status for one or all specs."""
        if spec_id:
            return self._active_devpods.get(spec_id, {"status": "not_found"})
        return dict(self._active_devpods)

    def list_devpods(self):
        """Return DevPod list for API consumption."""
        result = []
        for spec_id, info in self._active_devpods.items():
            result.append({
                "spec_id": spec_id,
                "name": info.get("name", ""),
                "status": info.get("status", "unknown"),
                "started_at": info.get("started_at", ""),
                "last_active": info.get("last_active", 0),
            })
        return result

    @property
    def active_count(self):
        return sum(1 for v in self._active_devpods.values() if v["status"] == "running")