#!/usr/bin/env python3
"""RAG query — retrieve relevant context for agent prompt injection (MEM-R4).

Queries Qdrant for:
- Similar past specs (title/AC vector similarity)
- Related ADRs (tag overlap)
- Past errors on similar files (path prefix)
"""

from halo.common.qdrant_client import QdrantClient
from halo.memory.rag_indexer import RagIndexer, EMBEDDING_DIM


class RagQuery:
    """Query Qdrant for context injection into agent prompts (MEM-R4)."""

    def __init__(self, qdrant_client=None, embedding_fn=None):
        self.qdrant = qdrant_client or QdrantClient(collection="halo-rag")
        self._indexer = RagIndexer(qdrant_client=self.qdrant, embedding_fn=embedding_fn)

    def retrieve_context(self, spec, limit=5):
        """Retrieve RAG context for a spec (MEM-R4).

        Returns a formatted string of similar specs, ADRs, and past errors.
        """
        query_text = f"{spec.title} {spec.body[:500]}"
        query_vector = self._indexer._embed(query_text)

        results = self.qdrant.search(query_vector, limit=limit, score_threshold=0.1)

        context_parts = []
        for hit in results:
            payload = hit.get("payload", {})
            doc_type = payload.get("type", "unknown")
            doc_id = payload.get("doc_id", payload.get("file", "unknown"))
            text = payload.get("text", "")
            score = hit.get("score", 0)

            if doc_type == "spec":
                context_parts.append(f"[Similar Spec: {doc_id}, score={score:.2f}] {text[:200]}")
            elif doc_type == "arch":
                context_parts.append(f"[Architecture: {doc_id}, score={score:.2f}] {text[:200]}")
            elif doc_type == "source":
                context_parts.append(f"[Related Code: {doc_id}, score={score:.2f}] {text[:200]}")
            else:
                context_parts.append(f"[{doc_type}: {doc_id}, score={score:.2f}] {text[:200]}")

        if not context_parts:
            return ""
        return "RAG Context:\n" + "\n\n".join(context_parts)

    def search_similar_specs(self, title, limit=3):
        """Search for specs with similar titles."""
        query_vector = self._indexer._embed(title)
        results = self.qdrant.search(query_vector, limit=limit, score_threshold=0.1)
        return [r for r in results if r.get("payload", {}).get("type") == "spec"]

    def search_related_adrs(self, tags, limit=3):
        """Search for ADRs matching tags."""
        query_text = " ".join(tags)
        query_vector = self._indexer._embed(query_text)
        results = self.qdrant.search(query_vector, limit=limit, score_threshold=0.1)
        return [r for r in results if r.get("payload", {}).get("type") == "arch"]

    def search_past_errors(self, file_path, limit=3):
        """Search for past errors on similar file paths."""
        query_vector = self._indexer._embed(file_path)
        results = self.qdrant.search(query_vector, limit=limit, score_threshold=0.05)
        return [r for r in results if r.get("payload", {}).get("type") == "source"]