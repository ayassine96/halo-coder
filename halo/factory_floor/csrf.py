#!/usr/bin/env python3
"""CSRF protection middleware for Factory Floor (SEC-6)."""

import secrets


class CSRFProtection:
    """Simple CSRF token manager for mutating endpoints (SEC-6)."""

    def __init__(self):
        self._tokens = set()

    def generate(self):
        """Generate a one-time CSRF token."""
        token = secrets.token_urlsafe(32)
        self._tokens.add(token)
        return token

    def verify(self, token):
        """Verify and consume a CSRF token."""
        if token and token in self._tokens:
            self._tokens.discard(token)
            return True
        return False

    def cleanup_expired(self, max_tokens=1000):
        """Prevent unbounded token growth."""
        if len(self._tokens) > max_tokens:
            self._tokens = set(list(self._tokens)[-max_tokens:])