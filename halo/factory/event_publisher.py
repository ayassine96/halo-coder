#!/usr/bin/env python3
"""Event publisher — Redis Pub/Sub with atomic Git+Redis (OR-R6, OR-NF2).

Channels: halo:factory:logs, halo:factory:approvals, halo:factory:alerts, halo:factory:metrics
Graceful degradation: if Redis is down, degrade to Git-only operation.
"""

from halo.common.models import CHANNEL_LOGS, CHANNEL_APPROVALS, CHANNEL_ALERTS, CHANNEL_METRICS


class EventPublisher:
    """Publish events to Redis Pub/Sub (OR-R6)."""

    def __init__(self, redis_client=None, log=None):
        self.redis = redis_client
        self.log = log
        self._redis_available = True

    def publish(self, channel, event_type, spec_id="", data=""):
        """Publish an event. Degrades gracefully if Redis is down (OR-NF2)."""
        from halo.common.models import EventMessage
        import json
        msg = EventMessage(channel=channel, event_type=event_type, spec_id=spec_id, data=str(data))
        if self.redis and self._redis_available:
            try:
                payload = json.dumps(msg.__dict__)
                self.redis.publish(channel, payload)
                if channel == CHANNEL_LOGS:
                    self.redis.lpush(f"{channel}:recent", payload)
                    self.redis.ltrim(f"{channel}:recent", 0, 499)
                return True
            except Exception as e:
                self._redis_available = False
                if self.log:
                    self.log.warning(f"Redis unavailable, degrading to Git-only: {e}")
                return False
        return False

    def log_event(self, spec_id, message):
        return self.publish(CHANNEL_LOGS, "log", spec_id=spec_id, data=message)

    def request_approval(self, spec_id, summary=""):
        return self.publish(CHANNEL_APPROVALS, "approval_request", spec_id=spec_id, data=summary)

    def alert(self, spec_id, message):
        return self.publish(CHANNEL_ALERTS, "alert", spec_id=spec_id, data=message)

    def metric(self, spec_id, metric_data):
        return self.publish(CHANNEL_METRICS, "metric", spec_id=spec_id, data=metric_data)

    def check_redis(self):
        """Check if Redis is available. Re-enable if it recovers."""
        if not self.redis:
            return False
        try:
            self.redis.ping()
            self._redis_available = True
            return True
        except Exception:
            self._redis_available = False
            return False