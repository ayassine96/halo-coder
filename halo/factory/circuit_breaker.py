#!/usr/bin/env python3
"""Circuit breaker for model backend failures (OR-R10).

If a model backend fails health checks, queue tasks and alert rather than silently dropping work.
"""

import time
from collections import defaultdict


class CircuitBreaker:
    """Circuit breaker for model backends (OR-R10)."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold=3, recovery_timeout=60, log=None):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.log = log
        self._states = defaultdict(lambda: self.CLOSED)
        self._failure_counts = defaultdict(int)
        self._last_failure = defaultdict(float)

    def record_success(self, model):
        """Record a successful request to a model backend."""
        self._states[model] = self.CLOSED
        self._failure_counts[model] = 0

    def record_failure(self, model):
        """Record a failed request. Opens circuit if threshold exceeded."""
        self._failure_counts[model] += 1
        self._last_failure[model] = time.time()
        if self._failure_counts[model] >= self.failure_threshold:
            self._states[model] = self.OPEN

    def can_proceed(self, model):
        """Check if requests can proceed for a model (OR-R10)."""
        state = self._states[model]
        if state == self.OPEN:
            if time.time() - self._last_failure[model] > self.recovery_timeout:
                self._states[model] = self.HALF_OPEN
                return True
            return False
        return True

    def get_state(self, model):
        """Return circuit state for a model."""
        return self._states[model]

    def reset(self, model=None):
        """Reset circuit for a model or all."""
        if model:
            self._states[model] = self.CLOSED
            self._failure_counts[model] = 0
        else:
            self._states.clear()
            self._failure_counts.clear()