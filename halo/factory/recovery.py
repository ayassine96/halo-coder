#!/usr/bin/env python3
"""Crash recovery + idempotency (OR-R8).

On restart, scan all in_progress specs, check DevPod liveness, and resume or fail deterministically.
"""

from halo.common.models import SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_FAILED_RED


class Recovery:
    """Crash recovery for the supervisor (OR-R8)."""

    def __init__(self, k3s_client=None, event_publisher=None, log=None):
        self.k3s = k3s_client
        self.event_publisher = event_publisher
        self.log = log

    def check_and_resume(self, spec_id, spec):
        """Check DevPod liveness and resume or fail (OR-R8)."""
        if not self.k3s:
            return "no_k3s"

        pod_name = f"halo-devpod-{spec_id.lower()}"
        status = self.k3s.get_deployment_status(pod_name)
        if status.get("ready"):
            if self.log:
                self.log.info(f"Resuming {spec_id} — DevPod is live", extra={"component": "recovery", "spec_id": spec_id})
            return "resumed"
        else:
            if self.event_publisher:
                self.event_publisher.alert(spec_id, f"DevPod {pod_name} not live — marking as failed")
            if self.log:
                self.log.warning(f"Failing {spec_id} — DevPod not live", extra={"component": "recovery", "spec_id": spec_id})
            return "failed"

    def scan_in_progress(self, specs):
        """Scan all in_progress specs and recover them (OR-R8)."""
        results = {"resumed": [], "failed": []}
        for spec_id, spec in specs.items():
            if spec.status == SPEC_STATUS_IN_PROGRESS:
                result = self.check_and_resume(spec_id, spec)
                if result == "resumed":
                    results["resumed"].append(spec_id)
                elif result == "failed":
                    results["failed"].append(spec_id)
        return results