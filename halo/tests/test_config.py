#!/usr/bin/env python3
"""Unit tests for halo.common.config."""

import os
import unittest
from unittest.mock import patch
from halo.common.config import HaloConfig


class TestHaloConfig(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_defaults(self):
        cfg = HaloConfig.from_env()
        self.assertEqual(cfg.redis_url, "redis://localhost:6379")
        self.assertEqual(cfg.k3s_api, "http://localhost:6443")
        self.assertEqual(cfg.projects_dir, "/var/halo/projects")
        self.assertEqual(cfg.kernel_url, "http://localhost:13305")
        self.assertEqual(cfg.minio_endpoint, "localhost:9000")
        self.assertFalse(cfg.minio_secure)
        self.assertEqual(cfg.qdrant_url, "http://localhost:6333")
        self.assertEqual(cfg.log_file, "/var/log/halo/factory.log")

    @patch.dict(os.environ, {
        "HALO_REDIS_URL": "redis://redis:6379",
        "HALO_PROJECTS_DIR": "/data/projects",
        "HALO_MINIO_SECURE": "true",
    })
    def test_env_overrides(self):
        cfg = HaloConfig.from_env()
        self.assertEqual(cfg.redis_url, "redis://redis:6379")
        self.assertEqual(cfg.projects_dir, "/data/projects")
        self.assertTrue(cfg.minio_secure)


if __name__ == '__main__':
    unittest.main()