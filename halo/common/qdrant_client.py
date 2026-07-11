#!/usr/bin/env python3
"""Qdrant client for RAG vector search."""

import json
import urllib.request
import urllib.error


class QdrantClient:
    """Lightweight Qdrant client using urllib (no external dep)."""

    def __init__(self, url="http://localhost:6333", collection="halo-rag"):
        self._url = url.rstrip("/")
        self._collection = collection

    def _request(self, method, path, data=None):
        url = f"{self._url}{path}"
        headers = {"Content-Type": "application/json"}
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8")) if resp.read() else {}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            raise

    def ensure_collection(self, vector_size=1024, distance="Cosine"):
        """Create collection if it doesn't exist."""
        if self.collection_exists():
            return
        self._request("PUT", f"/collections/{self._collection}", {
            "vectors": {"size": vector_size, "distance": distance}
        })

    def collection_exists(self):
        try:
            resp = self._request("GET", f"/collections/{self._collection}")
            return bool(resp)
        except urllib.error.HTTPError:
            return False

    def upsert(self, points, batch_size=100):
        """Upsert points [{id, vector, payload}] into collection."""
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self._request("PUT", f"/collections/{self._collection}/points", {"points": batch})

    def search(self, vector, limit=5, score_threshold=0.0):
        """Search for nearest vectors. Returns list of (id, score, payload)."""
        resp = self._request("POST", f"/collections/{self._collection}/points/search", {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
            "score_threshold": score_threshold,
        })
        results = []
        for hit in resp.get("result", []):
            results.append({
                "id": hit.get("id"),
                "score": hit.get("score"),
                "payload": hit.get("payload"),
            })
        return results

    def delete_collection(self):
        self._request("DELETE", f"/collections/{self._collection}")

    def count(self):
        resp = self._request("GET", f"/collections/{self._collection}")
        return resp.get("result", {}).get("points_count", 0)