#!/usr/bin/env python3
"""Unit tests for Factory Orchestrator (Stage 6 — OR-R1..OR-R10, WF-SPEC-1..15)."""

import unittest
from unittest.mock import MagicMock, patch, call
import time

from halo.factory.supervisor import Supervisor
from halo.factory.dispatcher import Dispatcher, ROLE_PLANNER, ROLE_CODER, ROLE_TESTER, ROLE_REVIEWER, ROLE_MERGER
from halo.factory.devpod_manager import DevPodManager, IDLE_THRESHOLD_SECONDS
from halo.factory.event_publisher import EventPublisher
from halo.factory.recovery import Recovery
from halo.factory.circuit_breaker import CircuitBreaker
from halo.factory.workflow import Workflow, TDDLoop, MAX_RETRIES
from halo.factory.alerts import AlertsManager
from halo.factory.agents.prompts import get_system_prompt, format_tdad_injection


class TestSupervisor(unittest.TestCase):

    def setUp(self):
        self.s = Supervisor()

    def test_init_defaults(self):
        self.assertFalse(self.s._running)
        self.assertFalse(self.s._paused)

    def test_pause_resume(self):
        self.s.pause()
        self.assertTrue(self.s._paused)
        self.s.resume()
        self.assertFalse(self.s._paused)

    def test_stop(self):
        self.s._running = True
        self.s.stop()
        self.assertFalse(self.s._running)

    def test_scan_no_dir(self):
        specs = self.s.scan_projects()
        self.assertEqual(specs, {})


class TestDispatcher(unittest.TestCase):

    def test_dispatch_planner(self):
        mock_redis = MagicMock()
        d = Dispatcher(mock_redis)
        task = d.dispatch_planner("SPEC-001", prompt="Plan it")
        self.assertEqual(task.role, "planner")
        self.assertEqual(task.model_profile, "halo-reasoning")
        mock_redis.stream_enqueue.assert_called_once()

    def test_dispatch_coder_with_tdad(self):
        mock_redis = MagicMock()
        d = Dispatcher(mock_redis)
        task = d.dispatch_coder("SPEC-001", tdad_tests=["tests/test_auth.py::test_login"])
        self.assertEqual(task.role, "coder")
        self.assertIn("test_login", task.prompt)

    def test_dispatch_all_roles(self):
        mock_redis = MagicMock()
        d = Dispatcher(mock_redis)
        for method, role in [(d.dispatch_planner, "planner"), (d.dispatch_coder, "coder"),
                              (d.dispatch_tester, "tester"), (d.dispatch_reviewer, "reviewer"),
                              (d.dispatch_merger, "merger")]:
            mock_redis.reset_mock()
            task = method("SPEC-001")
            self.assertEqual(task.role, role)
            mock_redis.stream_enqueue.assert_called_once()

    def test_dequeue(self):
        mock_redis = MagicMock()
        mock_redis.stream_dequeue.return_value = []
        d = Dispatcher(mock_redis)
        result = d.dequeue()
        self.assertEqual(result, [])

    def test_ack(self):
        mock_redis = MagicMock()
        d = Dispatcher(mock_redis)
        d.ack("12345")
        mock_redis.stream_ack.assert_called_once()


class TestDevPodManager(unittest.TestCase):

    def setUp(self):
        self.mgr = DevPodManager(max_devpods=2)

    def test_scale_up(self):
        name, err = self.mgr.scale_up("SPEC-001")
        self.assertIsNotNone(name)
        self.assertIsNone(err)
        self.assertEqual(self.mgr.active_count, 1)

    def test_max_devpods(self):
        self.mgr.scale_up("SPEC-001")
        self.mgr.scale_up("SPEC-002")
        name, err = self.mgr.scale_up("SPEC-003")
        self.assertIsNone(name)
        self.assertIn("Max", err)

    def test_scale_down(self):
        self.mgr.scale_up("SPEC-001")
        result = self.mgr.scale_down("SPEC-001")
        self.assertTrue(result)
        self.assertNotIn("SPEC-001", self._active_if_running())

    def _active_if_running(self):
        return {k: v for k, v in self.mgr._active_devpods.items() if v["status"] == "running"}

    def test_destroy(self):
        self.mgr.scale_up("SPEC-001")
        result = self.mgr.destroy("SPEC-001")
        self.assertTrue(result)
        self.assertNotIn("SPEC-001", self.mgr._active_devpods)

    def test_touch(self):
        self.mgr.scale_up("SPEC-001")
        old = self.mgr._active_devpods["SPEC-001"]["last_active"]
        time.sleep(0.01)
        self.mgr.touch("SPEC-001")
        self.assertGreater(self.mgr._active_devpods["SPEC-001"]["last_active"], old)

    def test_cleanup_idle(self):
        self.mgr.scale_up("SPEC-001")
        self.mgr._active_devpods["SPEC-001"]["last_active"] = time.time() - (IDLE_THRESHOLD_SECONDS + 1)
        destroyed = self.mgr.cleanup_idle()
        self.assertIn("SPEC-001", destroyed)

    def test_get_status(self):
        self.mgr.scale_up("SPEC-001")
        status = self.mgr.get_status("SPEC-001")
        self.assertEqual(status["status"], "running")
        all_status = self.mgr.get_status()
        self.assertIn("SPEC-001", all_status)


class TestEventPublisher(unittest.TestCase):

    def test_publish_success(self):
        mock_redis = MagicMock()
        pub = EventPublisher(mock_redis)
        result = pub.log_event("SPEC-001", "Started")
        self.assertTrue(result)
        mock_redis.publish.assert_called_once()

    def test_publish_redis_down(self):
        mock_redis = MagicMock()
        mock_redis.publish.side_effect = Exception("Redis down")
        pub = EventPublisher(mock_redis)
        result = pub.log_event("SPEC-001", "test")
        self.assertFalse(result)
        self.assertFalse(pub._redis_available)

    def test_request_approval(self):
        mock_redis = MagicMock()
        pub = EventPublisher(mock_redis)
        pub.request_approval("SPEC-001", "Ready")
        mock_redis.publish.assert_called_once()

    def test_alert(self):
        mock_redis = MagicMock()
        pub = EventPublisher(mock_redis)
        pub.alert("SPEC-001", "Failed")
        mock_redis.publish.assert_called_once()

    def test_check_redis(self):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        pub = EventPublisher(mock_redis)
        self.assertTrue(pub.check_redis())


class TestRecovery(unittest.TestCase):

    def test_resume_live_pod(self):
        mock_k3s = MagicMock()
        mock_k3s.get_deployment_status.return_value = {"exists": True, "ready": True, "replicas": 1}
        recovery = Recovery(mock_k3s)
        result = recovery.check_and_resume("SPEC-001", MagicMock())
        self.assertEqual(result, "resumed")

    def test_fail_dead_pod(self):
        mock_k3s = MagicMock()
        mock_k3s.get_deployment_status.return_value = {"exists": False, "ready": False, "replicas": 0}
        pub = MagicMock()
        recovery = Recovery(mock_k3s, pub)
        result = recovery.check_and_resume("SPEC-001", MagicMock())
        self.assertEqual(result, "failed")
        pub.alert.assert_called_once()

    def test_scan_in_progress(self):
        mock_k3s = MagicMock()
        mock_k3s.get_deployment_status.return_value = {"exists": True, "ready": True}
        recovery = Recovery(mock_k3s)
        specs = {"SPEC-001": MagicMock(status="in_progress"), "SPEC-002": MagicMock(status="draft")}
        results = recovery.scan_in_progress(specs)
        self.assertIn("SPEC-001", results["resumed"])
        self.assertNotIn("SPEC-002", results["resumed"])


class TestCircuitBreaker(unittest.TestCase):

    def test_starts_closed(self):
        cb = CircuitBreaker()
        self.assertEqual(cb.get_state("halo-reasoning"), "closed")

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure("halo-reasoning")
        self.assertEqual(cb.get_state("halo-reasoning"), "open")
        self.assertFalse(cb.can_proceed("halo-reasoning"))

    def test_closed_allows_proceed(self):
        cb = CircuitBreaker()
        self.assertTrue(cb.can_proceed("halo-reasoning"))

    def test_success_resets(self):
        cb = CircuitBreaker()
        cb.record_failure("halo-reasoning")
        cb.record_success("halo-reasoning")
        self.assertEqual(cb.get_state("halo-reasoning"), "closed")
        self.assertEqual(cb._failure_counts["halo-reasoning"], 0)

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure("halo-reasoning")
        self.assertEqual(cb.get_state("halo-reasoning"), "open")
        time.sleep(0.01)
        self.assertTrue(cb.can_proceed("halo-reasoning"))
        self.assertEqual(cb.get_state("halo-reasoning"), "half_open")


class TestWorkflow(unittest.TestCase):

    def setUp(self):
        self.dispatcher = MagicMock()
        self.devpod = MagicMock()
        self.pub = MagicMock()
        self.wf = Workflow(
            dispatcher=self.dispatcher, devpod_manager=self.devpod,
            event_publisher=self.pub,
        )

    def test_start_spec(self):
        spec = MagicMock(id="SPEC-001", title="Test", body="AC: stuff")
        self.wf.start_spec("SPEC-001", spec)
        self.devpod.scale_up.assert_called_once_with("SPEC-001")
        self.dispatcher.dispatch_planner.assert_called_once()

    def test_on_plan_complete(self):
        spec = MagicMock()
        self.wf.on_plan_complete("SPEC-001", spec)
        self.dispatcher.dispatch_coder.assert_called_once()

    def test_on_code_committed(self):
        spec = MagicMock()
        self.wf.on_code_committed("SPEC-001", spec)
        self.dispatcher.dispatch_tester.assert_called_once()

    def test_on_test_pass(self):
        spec = MagicMock()
        self.wf.on_test_complete("SPEC-001", spec, passed=True)
        self.dispatcher.dispatch_reviewer.assert_called_once()

    def test_on_test_fail_retry(self):
        spec = MagicMock()
        self.wf.on_test_complete("SPEC-001", spec, passed=False, failure_type="red")
        self.dispatcher.dispatch_coder.assert_called_once()
        self.assertEqual(self.wf._retry_counts["SPEC-001"], 1)

    def test_on_test_fail_max_retries(self):
        spec = MagicMock()
        self.wf._retry_counts["SPEC-001"] = MAX_RETRIES
        self.wf.on_test_complete("SPEC-001", spec, passed=False, failure_type="red")
        self.pub.alert.assert_called_once()
        self.dispatcher.dispatch_coder.assert_not_called()

    def test_on_review_approved(self):
        spec = MagicMock()
        self.wf.on_review_complete("SPEC-001", spec, approved=True)
        self.pub.request_approval.assert_called_once()

    def test_on_review_rejected(self):
        spec = MagicMock()
        self.wf.on_review_complete("SPEC-001", spec, approved=False)
        self.pub.alert.assert_called_once()

    def test_on_human_approved(self):
        spec = MagicMock()
        mock_git = MagicMock()
        self.wf.git_ops = mock_git
        self.wf.on_human_approved("SPEC-001", spec, acceptance_criteria="AC: test")
        self.dispatcher.dispatch_merger.assert_called_once()
        mock_git.squash_merge_spec.assert_called_once_with("SPEC-001", "AC: test")
        mock_git.delete_spec_branch.assert_called_once()

    def test_on_human_rejected(self):
        spec = MagicMock()
        self.wf.on_human_rejected("SPEC-001", spec, reason="bad")
        self.pub.log_event.assert_called_once()


class TestTDDLoop(unittest.TestCase):

    def test_full_cycle(self):
        loop = TDDLoop()
        loop.start("SPEC-001")
        self.assertEqual(loop.get_phase("SPEC-001"), "red")
        self.assertTrue(loop.verify_red("SPEC-001", tests_failed=True))
        self.assertEqual(loop.get_phase("SPEC-001"), "green")
        self.assertTrue(loop.verify_green("SPEC-001", tests_passed=True))
        self.assertEqual(loop.get_phase("SPEC-001"), "refactor")
        self.assertTrue(loop.complete_refactor("SPEC-001", tests_still_pass=True))
        self.assertIsNone(loop.get_phase("SPEC-001"))

    def test_red_not_verified(self):
        loop = TDDLoop()
        loop.start("SPEC-001")
        self.assertFalse(loop.verify_red("SPEC-001", tests_failed=False))
        self.assertEqual(loop.get_phase("SPEC-001"), "red")


class TestAlertsManager(unittest.TestCase):

    def test_no_url_returns_false(self):
        am = AlertsManager(ntfy_url="")
        self.assertFalse(am.send_alert("test", "msg"))

    def test_alert_failure_format(self):
        am = AlertsManager(ntfy_url="")
        self.assertFalse(am.alert_failure("SPEC-001", "red", "tests failed"))

    def test_alert_approval_format(self):
        am = AlertsManager(ntfy_url="")
        self.assertFalse(am.alert_approval_needed("SPEC-001", "ready"))


class TestAgentPrompts(unittest.TestCase):

    def test_all_roles_have_prompts(self):
        for role in ["planner", "coder", "tester", "reviewer", "merger"]:
            prompt = get_system_prompt(role)
            self.assertTrue(prompt)
            self.assertIn("HALO", prompt)

    def test_tdad_injection_format(self):
        injection = format_tdad_injection(["src/auth.py"], ["tests/test_auth.py::test_login"])
        self.assertIn("src/auth.py", injection)
        self.assertIn("test_login", injection)
        self.assertIn("MUST run these tests", injection)


if __name__ == '__main__':
    unittest.main()