#!/usr/bin/env python3
"""Redis client wrapping Streams (dispatch) and Pub/Sub (events)."""

import json

try:
    import redis
except ImportError:
    redis = None


class RedisClient:
    """Wrapper over redis-py for Streams + Pub/Sub."""

    def __init__(self, url="redis://localhost:6379", stream_group="halo-factory"):
        if redis is None:
            raise ImportError("redis-py is required: pip install redis")
        self._pool = redis.ConnectionPool.from_url(url, decode_responses=True)
        self._client = redis.Redis(connection_pool=self._pool)
        self._stream_group = stream_group

    @property
    def client(self):
        return self._client

    def publish(self, channel, message):
        """Publish to Pub/Sub channel."""
        return self._client.publish(channel, json.dumps(message) if isinstance(message, dict) else message)

    def subscribe(self, *channels):
        """Subscribe to Pub/Sub channels. Yields (channel, message) tuples."""
        pubsub = self._client.pubsub()
        pubsub.subscribe(*channels)
        for raw in pubsub.listen():
            if raw["type"] == "message":
                yield raw["channel"], raw["data"]

    def stream_enqueue(self, stream, fields):
        """Add to Redis Stream for dispatch queue."""
        return self._client.xadd(stream, {k: json.dumps(v) if isinstance(v, dict) else str(v) for k, v in fields.items()})

    def stream_dequeue(self, stream, count=1, block_ms=0):
        """Read from Stream via consumer group."""
        try:
            self._client.xgroup_create(stream, self._stream_group, id="$", mkstream=True)
        except redis.ResponseError:
            pass
        return self._client.xreadgroup(self._stream_group, "worker", {stream: ">"}, count=count, block=block_ms)

    def stream_ack(self, stream, message_id):
        """Acknowledge a stream message."""
        return self._client.xack(stream, self._stream_group, message_id)

    def stream_len(self, stream):
        return self._client.xlen(stream)

    def ping(self):
        return self._client.ping()

    def close(self):
        self._client.close()