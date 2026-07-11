#!/usr/bin/env python3
"""Spec file parser — YAML frontmatter + Markdown body (GIT-R1).

Spec format:
    ---
    id: SPEC-001
    title: "Hello World FastAPI Endpoint"
    status: draft
    depends_on: [SPEC-000]
    blocks: [SPEC-002]
    tags: [api, fastapi, tdd]
    author: halo-agent
    created_at: 2026-07-11T00:00:00Z
    ---
    # Body markdown...
"""

import os
import re

try:
    import yaml
except ImportError:
    yaml = None

from halo.common.models import Spec, SPEC_STATUS_DRAFT


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_REQUIRED_FIELDS = {"id", "title", "status"}


class SpecParseError(Exception):
    pass


class SpecValidationError(Exception):
    pass


def parse_spec_file(file_path):
    """Parse a spec file from disk. Returns a Spec object."""
    with open(file_path, "r") as f:
        content = f.read()
    return parse_spec_content(content, file_path)


def parse_spec_content(content, file_path=""):
    """Parse spec content string. Returns a Spec object."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise SpecParseError(f"No YAML frontmatter found in {file_path}")

    frontmatter_text, body = match.group(1), match.group(2).strip()

    if yaml is None:
        frontmatter = _parse_simple_yaml(frontmatter_text)
    else:
        frontmatter = yaml.safe_load(frontmatter_text)

    if not isinstance(frontmatter, dict):
        raise SpecParseError(f"Frontmatter is not a dict in {file_path}")

    missing = _REQUIRED_FIELDS - set(frontmatter.keys())
    if missing:
        raise SpecValidationError(f"Missing required fields in {file_path}: {missing}")

    return Spec(
        id=frontmatter["id"],
        title=frontmatter["title"],
        status=frontmatter["status"],
        depends_on=frontmatter.get("depends_on", []),
        blocks=frontmatter.get("blocks", []),
        tags=frontmatter.get("tags", []),
        author=frontmatter.get("author", "halo-agent"),
        created_at=frontmatter.get("created_at", ""),
        body=body,
        file_path=file_path,
    )


def _parse_simple_yaml(text):
    """Minimal YAML parser for flat key: value with list support."""
    result = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [v.strip().strip('"\'') for v in val[1:-1].split(",") if v.strip()]
                result[key] = items
            elif val.startswith('"') and val.endswith('"'):
                result[key] = val[1:-1]
            elif val.startswith("'") and val.endswith("'"):
                result[key] = val[1:-1]
            else:
                result[key] = val
    return result


def parse_specs_dir(specs_dir):
    """Parse all SPEC-*.md files in a directory."""
    specs = {}
    if not os.path.isdir(specs_dir):
        return specs
    for fname in sorted(os.listdir(specs_dir)):
        if fname.startswith("SPEC-") and fname.endswith(".md"):
            path = os.path.join(specs_dir, fname)
            try:
                spec = parse_spec_file(path)
                specs[spec.id] = spec
            except (SpecParseError, SpecValidationError):
                pass
    return specs


def validate_spec(spec):
    """Validate a parsed spec (required fields, status value)."""
    from halo.common.models import ALL_STATUSES
    if spec.status not in ALL_STATUSES:
        raise SpecValidationError(f"Invalid status '{spec.status}' in {spec.id}")
    if not spec.id.startswith("SPEC-"):
        raise SpecValidationError(f"Spec id must start with 'SPEC-' in {spec.id}")
    return True