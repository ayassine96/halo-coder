#!/usr/bin/env python3
"""Unit tests for halo.specs.parser (GIT-R1)."""

import os
import tempfile
import unittest

from halo.specs.parser import (
    parse_spec_content, parse_spec_file, parse_specs_dir,
    validate_spec, SpecParseError, SpecValidationError,
)


SAMPLE_SPEC = """---
id: SPEC-001
title: "Hello World FastAPI Endpoint"
status: draft
depends_on: [SPEC-000]
blocks: [SPEC-002]
tags: [api, fastapi, tdd]
author: halo-agent
created_at: 2026-07-11T00:00:00Z
---
# SPEC-001: Hello World

## Acceptance Criteria

- GET / returns 200
- Response is JSON
"""

SAMPLE_NO_FRONTMATTER = "# Just a markdown file\n\nNo frontmatter."


class TestParseSpecContent(unittest.TestCase):

    def test_parse_valid(self):
        spec = parse_spec_content(SAMPLE_SPEC, "SPEC-001.md")
        self.assertEqual(spec.id, "SPEC-001")
        self.assertEqual(spec.title, "Hello World FastAPI Endpoint")
        self.assertEqual(spec.status, "draft")
        self.assertEqual(spec.depends_on, ["SPEC-000"])
        self.assertEqual(spec.blocks, ["SPEC-002"])
        self.assertEqual(spec.tags, ["api", "fastapi", "tdd"])
        self.assertEqual(spec.author, "halo-agent")
        self.assertIn("Hello World", spec.body)

    def test_parse_missing_frontmatter(self):
        with self.assertRaises(SpecParseError):
            parse_spec_content(SAMPLE_NO_FRONTMATTER)

    def test_parse_missing_required_fields(self):
        content = "---\nid: SPEC-001\n---\nbody"
        with self.assertRaises(SpecValidationError):
            parse_spec_content(content)

    def test_parse_no_deps(self):
        content = "---\nid: SPEC-001\ntitle: Test\nstatus: draft\n---\nbody"
        spec = parse_spec_content(content)
        self.assertEqual(spec.depends_on, [])
        self.assertEqual(spec.blocks, [])


class TestParseSpecFile(unittest.TestCase):

    def test_parse_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, dir="/tmp") as f:
            f.write(SAMPLE_SPEC)
            f.flush()
            spec = parse_spec_file(f.name)
            self.assertEqual(spec.id, "SPEC-001")
            os.unlink(f.name)


class TestParseSpecsDir(unittest.TestCase):

    def test_parse_dir(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(3):
                path = os.path.join(d, f"SPEC-00{i}.md")
                with open(path, "w") as f:
                    f.write(f"---\nid: SPEC-00{i}\ntitle: Test {i}\nstatus: draft\n---\nbody {i}")
            specs = parse_specs_dir(d)
            self.assertEqual(len(specs), 3)
            self.assertIn("SPEC-000", specs)
            self.assertIn("SPEC-002", specs)

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            specs = parse_specs_dir(d)
            self.assertEqual(specs, {})

    def test_nonexistent_dir(self):
        specs = parse_specs_dir("/nonexistent")
        self.assertEqual(specs, {})


class TestValidateSpec(unittest.TestCase):

    def test_valid(self):
        spec = parse_spec_content(SAMPLE_SPEC)
        self.assertTrue(validate_spec(spec))

    def test_invalid_status(self):
        spec = parse_spec_content(SAMPLE_SPEC)
        spec.status = "bogus"
        with self.assertRaises(SpecValidationError):
            validate_spec(spec)

    def test_invalid_id_prefix(self):
        spec = parse_spec_content(SAMPLE_SPEC)
        spec.id = "NOT-SPEC"
        with self.assertRaises(SpecValidationError):
            validate_spec(spec)


if __name__ == '__main__':
    unittest.main()