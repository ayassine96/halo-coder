#!/usr/bin/env python3
"""ARCH.md manager — read, update, validate (GIT-R3)."""

import os
import re


_SECTION_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


class ArchManager:
    """Manage the ARCH.md file at a project root."""

    def __init__(self, project_dir):
        self.path = os.path.join(project_dir, "ARCH.md")

    def exists(self):
        return os.path.isfile(self.path)

    def read(self):
        """Return ARCH.md content as string."""
        if not self.exists():
            return ""
        with open(self.path, "r") as f:
            return f.read()

    def write(self, content):
        """Write/update ARCH.md content."""
        with open(self.path, "w") as f:
            f.write(content)

    def append_section(self, heading, body):
        """Append a new section to ARCH.md."""
        existing = self.read()
        section = f"\n\n## {heading}\n\n{body}\n"
        self.write(existing + section)
        return self.read()

    def get_sections(self):
        """Parse ARCH.md into a dict of heading → content."""
        content = self.read()
        if not content:
            return {}
        sections = {}
        parts = re.split(r"(^#{1,3}\s+.+$)", content, flags=re.MULTILINE)
        current_heading = None
        for part in parts:
            if re.match(r"^#{1,3}\s+", part):
                current_heading = part.strip().lstrip("#").strip()
            else:
                if current_heading:
                    sections[current_heading] = part.strip()
        return sections

    def ensure_exists(self, project_name=""):
        """Create a minimal ARCH.md if it doesn't exist."""
        if not self.exists():
            template = f"# Architecture — {project_name}\n\n## Overview\n\n[Project architecture overview]\n"
            self.write(template)
            return True
        return False