#!/usr/bin/env python3
"""Qdrant RAG indexer — embed specs, ADRs, code into vector DB (MEM-R1..R3).

Embedding model: BAAI/bge-large-en-v1.5 (dim=1024).
Rebuildable from Git: re-index all ARCH.md, specs/, src/ within 30 min (MEM-R3).
"""

import os
import hashlib
import json
from halo.common.qdrant_client import QdrantClient

EMBEDDING_DIM = 1024
COLLECTION_NAME = "halo-rag"


class RagIndexer:
    """Embed documents into Qdrant for vector search (MEM-R1, MEM-R3)."""

    def __init__(self, qdrant_client=None, embedding_fn=None):
        self.qdrant = qdrant_client or QdrantClient(collection=COLLECTION_NAME)
        self._embed = embedding_fn or self._default_embedding

    def _default_embedding(self, text):
        """Default embedding: deterministic hash-based placeholder vector.

        In production, replace with BAAI/bge-large-en-v1.5 or nomic-embed-text-v1.5.
        """
        h = hashlib.sha256(text.encode()).digest()
        vec = [float(b) / 255.0 for b in h * (EMBEDDING_DIM // 32 + 1)]
        return vec[:EMBEDDING_DIM]

    def ensure_collection(self):
        """Create the Qdrant collection if needed."""
        self.qdrant.ensure_collection(vector_size=EMBEDDING_DIM, distance="Cosine")

    def index_document(self, doc_id, text, metadata=None):
        """Embed and upsert a single document."""
        vector = self._embed(text)
        point = {
            "id": self._hash_id(doc_id),
            "vector": vector,
            "payload": {
                "doc_id": doc_id,
                "text": text[:500],
                **(metadata or {}),
            },
        }
        self.qdrant.upsert([point])
        return point["id"]

    def index_specs(self, specs_dir):
        """Index all spec files from a directory (MEM-R4)."""
        count = 0
        if not os.path.isdir(specs_dir):
            return 0
        for fname in sorted(os.listdir(specs_dir)):
            if fname.startswith("SPEC-") and fname.endswith(".md"):
                path = os.path.join(specs_dir, fname)
                with open(path, "r") as f:
                    content = f.read()
                self.index_document(
                    doc_id=fname,
                    text=content,
                    metadata={"type": "spec", "file": fname},
                )
                count += 1
        return count

    def index_arch(self, project_dir):
        """Index ARCH.md from a project root (MEM-R4)."""
        arch_path = os.path.join(project_dir, "ARCH.md")
        if not os.path.isfile(arch_path):
            return 0
        with open(arch_path, "r") as f:
            content = f.read()
        self.index_document(
            doc_id="ARCH.md",
            text=content,
            metadata={"type": "arch", "project": os.path.basename(project_dir)},
        )
        return 1

    def index_source_files(self, src_dir, max_files=500):
        """Index source code files (MEM-R3 — rebuildable from Git)."""
        count = 0
        for root, dirs, files in os.walk(src_dir):
            if count >= max_files:
                break
            dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "node_modules", ".venv"}]
            for fn in files:
                if fn.endswith((".py", ".ts", ".js", ".go", ".rs")):
                    path = os.path.join(root, fn)
                    try:
                        with open(path, "r") as f:
                            content = f.read()
                        rel_path = os.path.relpath(path, src_dir)
                        self.index_document(
                            doc_id=rel_path,
                            text=content,
                            metadata={"type": "source", "file": rel_path},
                        )
                        count += 1
                    except (IOError, UnicodeDecodeError):
                        continue
                    if count >= max_files:
                        break
        return count

    def rebuild_from_git(self, project_dir):
        """Full rebuild from Git state (MEM-R3 — within 30 min)."""
        self.ensure_collection()
        total = 0
        total += self.index_arch(project_dir)
        specs_dir = os.path.join(project_dir, "specs")
        total += self.index_specs(specs_dir)
        src_dir = os.path.join(project_dir, "src")
        total += self.index_source_files(src_dir)
        return total

    def _hash_id(self, text):
        """Create a stable integer ID from a string."""
        return int(hashlib.md5(text.encode()).hexdigest()[:15], 16)