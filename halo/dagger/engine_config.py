#!/usr/bin/env python3
"""Dagger engine configuration (DAG-R6, DAG-R1)."""

DEFAULT_CPU_LIMIT = 4
DEFAULT_RAM_LIMIT_GB = 8
PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright/python:v1.45.0-jammy"
CACHE_TTL = 3600  # seconds


def build_pipeline_config(cpu=DEFAULT_CPU_LIMIT, ram=DEFAULT_RAM_LIMIT_GB):
    """Return config dict for a Dagger pipeline invocation."""
    return {
        "cpu_limit": f"{cpu}",
        "ram_limit": f"{ram}Gi",
        "playwright_image": PLAYWRIGHT_IMAGE,
        "cache_ttl": CACHE_TTL,
    }