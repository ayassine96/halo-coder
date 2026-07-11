#!/usr/bin/env python3
"""K3s API wrapper for DevPod lifecycle management."""

import json
import subprocess


class K3sClient:
    """K3s API via kubectl subprocess (matches kube-coder pattern)."""

    def __init__(self, namespace=None):
        self._namespace = namespace

    def _kubectl(self, *args, capture=True, check=True):
        cmd = ["kubectl"]
        if self._namespace:
            cmd.extend(["-n", self._namespace])
        cmd.extend(args)
        result = subprocess.run(cmd, capture_output=capture, text=True)
        if check and result.returncode != 0:
            raise RuntimeError(f"kubectl failed: {result.stderr}")
        return result

    def scale_deployment(self, name, replicas):
        """Scale a deployment to N replicas."""
        return self._kubectl("scale", "deployment", name, f"--replicas={replicas}")

    def get_deployment_status(self, name):
        """Return dict with deployment status info."""
        result = self._kubectl("get", "deployment", name, "-o", "json", check=False)
        if result.returncode != 0:
            return {"exists": False, "ready": False, "replicas": 0}
        info = json.loads(result.stdout)
        return {
            "exists": True,
            "ready": info.get("status", {}).get("readyReplicas", 0) > 0,
            "replicas": info.get("status", {}).get("readyReplicas", 0),
            "desired": info.get("spec", {}).get("replicas", 0),
        }

    def list_pods(self, label_selector=None):
        """List pods matching label selector."""
        args = ["get", "pods", "-o", "json"]
        if label_selector:
            args.extend(["-l", label_selector])
        result = self._kubectl(*args, check=False)
        if result.returncode != 0:
            return []
        info = json.loads(result.stdout)
        return [
            {
                "name": p["metadata"]["name"],
                "phase": p.get("status", {}).get("phase", "Unknown"),
                "namespace": p["metadata"]["namespace"],
            }
            for p in info.get("items", [])
        ]

    def delete_pod(self, name):
        """Force-delete a pod."""
        return self._kubectl("delete", "pod", name, "--force", "--grace-period=0", check=False)

    def get_pod_logs(self, name, container=None, tail=100):
        """Get pod logs."""
        args = ["logs", name]
        if container:
            args.extend(["-c", container])
        args.extend(["--tail", str(tail)])
        result = self._kubectl(*args, check=False)
        return result.stdout if result.returncode == 0 else ""