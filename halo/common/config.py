#!/usr/bin/env python3
"""Environment configuration loader for HALO Factory services."""

import os
from dataclasses import dataclass


@dataclass
class HaloConfig:
    """Resolved configuration from environment variables."""
    redis_url: str
    k3s_api: str
    projects_dir: str
    kernel_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    qdrant_url: str
    log_file: str
    ntfy_url: str

    @classmethod
    def from_env(cls):
        return cls(
            redis_url=os.environ.get("HALO_REDIS_URL", "redis://localhost:6379"),
            k3s_api=os.environ.get("HALO_K3S_API", "http://localhost:6443"),
            projects_dir=os.environ.get("HALO_PROJECTS_DIR", "/var/halo/projects"),
            kernel_url=os.environ.get("HALO_KERNEL_URL", "http://localhost:13305"),
            minio_endpoint=os.environ.get("HALO_MINIO_ENDPOINT", "localhost:9000"),
            minio_access_key=os.environ.get("HALO_MINIO_ACCESS_KEY", "halo-admin"),
            minio_secret_key=os.environ.get("HALO_MINIO_SECRET_KEY", ""),
            minio_secure=os.environ.get("HALO_MINIO_SECURE", "false").lower() == "true",
            qdrant_url=os.environ.get("HALO_QDRANT_URL", "http://localhost:6333"),
            log_file=os.environ.get("HALO_LOG_FILE", "/var/log/halo/factory.log"),
            ntfy_url=os.environ.get("HALO_NTFY_URL", ""),
        )