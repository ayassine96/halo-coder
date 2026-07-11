#!/usr/bin/env python3
"""ntfy alert integration (INT-EXT-4)."""

import json
import urllib.request


class AlertsManager:
    """Send alerts via ntfy for failed states and approval requests (INT-EXT-4)."""

    def __init__(self, ntfy_url="", topic="halo-factory", log=None):
        self.url = ntfy_url.rstrip("/")
        self.topic = topic
        self.log = log

    def send_alert(self, title, message, priority="default", tags=""):
        """Send an alert to ntfy."""
        if not self.url:
            return False
        url = f"{self.url}/{self.topic}"
        headers = {
            "Title": title,
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = tags
        req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers, method="POST")
        try:
            urllib.request.urlopen(req)
            return True
        except Exception as e:
            if self.log:
                self.log.warning(f"ntfy alert failed: {e}")
            return False

    def alert_failure(self, spec_id, failure_type, message=""):
        """Alert on spec failure."""
        return self.send_alert(
            title=f"[FAILED] {spec_id} — {failure_type}",
            message=message or f"Spec {spec_id} failed at {failure_type} stage",
            priority="urgent",
            tags="warning,failed",
        )

    def alert_approval_needed(self, spec_id, summary=""):
        """Alert on approval needed."""
        return self.send_alert(
            title=f"[APPROVAL NEEDED] {spec_id}",
            message=summary,
            priority="default",
            tags="check,approval",
        )