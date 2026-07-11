#!/usr/bin/env python3
"""Unit tests for halo.common.qdrant_client (mocked)."""

import json
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
import io
from halo.common.qdrant_client import QdrantClient


class TestQdrantClient(unittest.TestCase):

    def test_default_collection(self):
        client = QdrantClient()
        self.assertEqual(client._collection, "halo-rag")
        self.assertEqual(client._url, "http://localhost:6333")

    @patch.object(QdrantClient, "_request")
    def test_ensure_collection_creates(self, mock_req):
        mock_req.return_value = {}
        client = QdrantClient()
        client.ensure_collection(vector_size=1024)
        self.assertGreaterEqual(mock_req.call_count, 1)

    @patch.object(QdrantClient, "_request")
    def test_search(self, mock_req):
        mock_req.return_value = {
            "result": [{"id": 1, "score": 0.95, "payload": {"title": "test"}}]
        }
        client = QdrantClient()
        results = client.search([0.1] * 1024, limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["score"], 0.95)

    @patch.object(QdrantClient, "_request")
    def test_upsert(self, mock_req):
        client = QdrantClient()
        points = [{"id": 1, "vector": [0.1] * 1024, "payload": {"text": "hello"}}]
        client.upsert(points)
        mock_req.assert_called()

    @patch.object(QdrantClient, "_request")
    def test_count(self, mock_req):
        mock_req.return_value = {"result": {"points_count": 42}}
        client = QdrantClient()
        self.assertEqual(client.count(), 42)


if __name__ == '__main__':
    unittest.main()