#!/usr/bin/env python3
"""Unit tests for halo.common.redis_client (mocked)."""

import json
import unittest
from unittest.mock import MagicMock, patch
from halo.common.redis_client import RedisClient


class TestRedisClient(unittest.TestCase):

    @patch("halo.common.redis_client.redis")
    def test_publish(self, mock_redis):
        mock_client = MagicMock()
        mock_redis.Redis.return_value = mock_client
        mock_redis.ConnectionPool.from_url.return_value = MagicMock()
        rc = RedisClient()
        rc.publish("halo:factory:logs", {"event": "test"})
        mock_client.publish.assert_called_once()
        args = mock_client.publish.call_args
        self.assertIn("halo:factory:logs", args[0])

    @patch("halo.common.redis_client.redis")
    def test_stream_enqueue(self, mock_redis):
        mock_client = MagicMock()
        mock_redis.Redis.return_value = mock_client
        mock_redis.ConnectionPool.from_url.return_value = MagicMock()
        rc = RedisClient()
        rc.stream_enqueue("halo:factory:queue", {"spec_id": "SPEC-001", "role": "planner"})
        mock_client.xadd.assert_called_once()

    @patch("halo.common.redis_client.redis")
    def test_stream_dequeue_creates_group(self, mock_redis):
        mock_client = MagicMock()
        mock_redis.Redis.return_value = mock_client
        mock_redis.ConnectionPool.from_url.return_value = MagicMock()
        mock_redis.ResponseError = Exception
        rc = RedisClient()
        rc.stream_dequeue("halo:factory:queue")
        mock_client.xgroup_create.assert_called_once()
        mock_client.xreadgroup.assert_called_once()

    @patch("halo.common.redis_client.redis")
    def test_stream_ack(self, mock_redis):
        mock_client = MagicMock()
        mock_redis.Redis.return_value = mock_client
        mock_redis.ConnectionPool.from_url.return_value = MagicMock()
        rc = RedisClient()
        rc.stream_ack("halo:factory:queue", "12345")
        mock_client.xack.assert_called_once_with("halo:factory:queue", "halo-factory", "12345")

    @patch("halo.common.redis_client.redis")
    def test_ping(self, mock_redis):
        mock_client = MagicMock()
        mock_redis.Redis.return_value = mock_client
        mock_redis.ConnectionPool.from_url.return_value = MagicMock()
        rc = RedisClient()
        rc.ping()
        mock_client.ping.assert_called_once()


if __name__ == '__main__':
    unittest.main()