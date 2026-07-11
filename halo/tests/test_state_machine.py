#!/usr/bin/env python3
"""Unit tests for halo.specs.state_machine (OR-R2)."""

import unittest

from halo.specs.state_machine import (
    can_transition, transition, get_legal_transitions, is_terminal, is_failed,
    InvalidTransitionError,
)
from halo.common.models import (
    SPEC_STATUS_DRAFT, SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS,
    SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED,
    SPEC_STATUS_FAILED_RED, SPEC_STATUS_FAILED_GREEN, SPEC_STATUS_FAILED_E2E,
)


class TestLegalTransitions(unittest.TestCase):

    def test_draft_to_ready(self):
        self.assertTrue(can_transition(SPEC_STATUS_DRAFT, SPEC_STATUS_READY))

    def test_ready_to_in_progress(self):
        self.assertTrue(can_transition(SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS))

    def test_in_progress_to_implemented(self):
        self.assertTrue(can_transition(SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_IMPLEMENTED))

    def test_in_progress_to_failed(self):
        self.assertTrue(can_transition(SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_FAILED_RED))
        self.assertTrue(can_transition(SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_FAILED_GREEN))
        self.assertTrue(can_transition(SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_FAILED_E2E))

    def test_implemented_to_merged(self):
        self.assertTrue(can_transition(SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED))

    def test_implemented_to_draft_reject(self):
        self.assertTrue(can_transition(SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_DRAFT))

    def test_failed_to_ready_retry(self):
        self.assertTrue(can_transition(SPEC_STATUS_FAILED_RED, SPEC_STATUS_READY))
        self.assertTrue(can_transition(SPEC_STATUS_FAILED_GREEN, SPEC_STATUS_DRAFT))

    def test_merge_is_terminal(self):
        self.assertTrue(is_terminal(SPEC_STATUS_MERGED))

    def test_reject_reverse(self):
        self.assertFalse(can_transition(SPEC_STATUS_MERGED, SPEC_STATUS_DRAFT))


class TestIllegalTransitions(unittest.TestCase):

    def test_ready_to_merged(self):
        self.assertFalse(can_transition(SPEC_STATUS_READY, SPEC_STATUS_MERGED))

    def test_draft_to_in_progress(self):
        self.assertFalse(can_transition(SPEC_STATUS_DRAFT, SPEC_STATUS_IN_PROGRESS))

    def test_merged_to_anything(self):
        self.assertFalse(can_transition(SPEC_STATUS_MERGED, SPEC_STATUS_DRAFT))


class TestTransitionFunction(unittest.TestCase):

    def test_valid_transition_returns_prefix(self):
        new_status, prefix = transition(SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS)
        self.assertEqual(new_status, SPEC_STATUS_IN_PROGRESS)
        self.assertEqual(prefix, "agent: start")

    def test_invalid_transition_raises(self):
        with self.assertRaises(InvalidTransitionError):
            transition(SPEC_STATUS_DRAFT, SPEC_STATUS_MERGED)

    def test_approve_prefix(self):
        _, prefix = transition(SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED)
        self.assertEqual(prefix, "human: approve")

    def test_reject_prefix(self):
        _, prefix = transition(SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_DRAFT)
        self.assertEqual(prefix, "human: reject")


class TestHelperFunctions(unittest.TestCase):

    def test_get_legal_transitions(self):
        t = get_legal_transitions(SPEC_STATUS_IN_PROGRESS)
        self.assertIn(SPEC_STATUS_IMPLEMENTED, t)
        self.assertIn(SPEC_STATUS_FAILED_RED, t)

    def test_is_failed(self):
        self.assertTrue(is_failed(SPEC_STATUS_FAILED_RED))
        self.assertTrue(is_failed(SPEC_STATUS_FAILED_GREEN))
        self.assertFalse(is_failed(SPEC_STATUS_DRAFT))

    def test_is_terminal_merged(self):
        self.assertTrue(is_terminal(SPEC_STATUS_MERGED))

    def test_is_terminal_not_others(self):
        self.assertFalse(is_terminal(SPEC_STATUS_DRAFT))


if __name__ == '__main__':
    unittest.main()