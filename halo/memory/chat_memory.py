#!/usr/bin/env python3
"""Chat memory rotation — memory.jsonl management with 10MB rotation (MEM-NF3).

Wraps Nanoclaw's memory.jsonl, ensuring rotation and providing query interface.
"""

import os
import json

from halo.nanoclaw.memory import MemoryFile, ROTATE_SIZE


class ChatMemory:
    """Manage chat memory with rotation (MEM-R2, MEM-NF3)."""

    def __init__(self, memory_path=None):
        self.path = memory_path or os.path.expanduser("~/memory.jsonl")
        self._file = MemoryFile(self.path)

    def append(self, role, content, metadata=None):
        """Append a chat message to memory.jsonl."""
        entry = {"role": role, "content": content}
        if metadata:
            entry["metadata"] = metadata
        self._file.append(entry)

    def recent(self, count=10):
        """Get the last N messages."""
        return self._file.read_recent(count)

    def all_messages(self):
        """Get all messages."""
        return self._file.read_all()

    def search(self, keyword):
        """Search messages for a keyword."""
        results = []
        for entry in self._file.read_all():
            if keyword.lower() in entry.get("content", "").lower():
                results.append(entry)
        return results

    def size(self):
        """Return file size in bytes."""
        return self._file.size()

    def is_rotation_needed(self):
        """Check if file is approaching rotation threshold."""
        return self.size() >= ROTATE_SIZE * 0.9

    def clear(self):
        """Clear all memory."""
        self._file.clear()