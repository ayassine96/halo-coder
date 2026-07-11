#!/usr/bin/env python3
"""memory.jsonl management — append-only, rotated at 10MB (MEM-NF3, MEM-R2)."""

import os
import json

ROTATE_SIZE = 10 * 1024 * 1024  # 10 MB


class MemoryFile:
    """Append-only memory.jsonl with rotation (MEM-NF3)."""

    def __init__(self, path):
        self.path = path
        self._ensure_dir()

    def _ensure_dir(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)

    def append(self, entry):
        """Append a JSON entry to memory.jsonl."""
        self._rotate_if_needed()
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_recent(self, count=10):
        """Read the last N entries from memory.jsonl."""
        if not os.path.exists(self.path):
            return []
        entries = []
        with open(self.path, "r") as f:
            for line in f:
                try:
                    entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return entries[-count:]

    def read_all(self):
        """Read all entries."""
        if not os.path.exists(self.path):
            return []
        entries = []
        with open(self.path, "r") as f:
            for line in f:
                try:
                    entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return entries

    def size(self):
        """Return current file size in bytes."""
        return os.path.getsize(self.path) if os.path.exists(self.path) else 0

    def _rotate_if_needed(self):
        """Rotate the file if it exceeds ROTATE_SIZE (MEM-NF3)."""
        if self.size() >= ROTATE_SIZE:
            rotated = self.path + ".1"
            if os.path.exists(rotated):
                os.unlink(rotated)
            os.rename(self.path, rotated)

    def clear(self):
        """Clear all memory."""
        if os.path.exists(self.path):
            os.unlink(self.path)